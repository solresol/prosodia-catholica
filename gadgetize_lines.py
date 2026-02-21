#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime, timezone

from openai import OpenAI

from db import get_connection
from openai_utils import load_openai_api_key


SYSTEM_PROMPT = (
    "You are a classical philologist and an expert at small, self-contained educational web gadgets. "
    "Given a Greek passage and its English translation, you will produce a tiny interactive toy in "
    "vanilla HTML/CSS/JavaScript that helps a reader play with the linguistic/prosodic idea in the passage."
)

USER_PROMPT = """Create a small interactive web gadget based on this passage of Aelius Herodianus (Περὶ καθολικῆς προσῳδίας).

The gadget should be *fun and useful*, but it does not need to be academically perfect. It should:
- Be fully self-contained and run offline (no external JS/CSS, no network calls).
- Use vanilla JS (no frameworks).
- Include at least one text input (Greek word or short phrase) and show some transformation/output.
- Prefer to demonstrate something that is plausibly connected to the passage (e.g., endings, accent/prosody patterns, ethnic/place-name morphology).
- Include brief instructions in the UI.

Output format rules (strict):
- Return JSON via the tool call with three strings: html, css, js.
- `html` should be BODY contents only (no <html>, <head>, <body> tags).
- `css` should be raw CSS (no <style> tags).
- `js` should be raw JavaScript (no <script> tags).
- Do not include any <script>, <style>, <link>, <iframe>, <object>, <embed> tags in html.
- Do not include any URLs, fetch(), XMLHttpRequest, or WebSocket usage.

Passage ref: {ref}
Greek text:
{greek_text}

English translation:
{english_translation}
"""


GADGET_TOOL = {
    "type": "function",
    "function": {
        "name": "generate_gadget",
        "description": "Generate a tiny self-contained HTML/CSS/JS gadget for a passage.",
        "parameters": {
            "type": "object",
            "properties": {
                "html": {"type": "string"},
                "css": {"type": "string"},
                "js": {"type": "string"},
            },
            "required": ["html", "css", "js"],
        },
    },
}


def _load_model(default: str) -> str:
    try:
        from config import GADGET_MODEL as CONFIG_GADGET_MODEL
    except ImportError:
        CONFIG_GADGET_MODEL = None
    return (CONFIG_GADGET_MODEL or default).strip()


_FORBIDDEN_HTML_RE = re.compile(
    r"<\s*(script|style|link|iframe|object|embed)\b", re.IGNORECASE
)
_FORBIDDEN_JS_RE = re.compile(
    r"\b(fetch|XMLHttpRequest|WebSocket)\b|\bimport\s*\(",
    re.IGNORECASE,
)
_URL_RE = re.compile(r"https?://", re.IGNORECASE)


def _validate_gadget(*, html: str, css: str, js: str) -> None:
    combined = f"{html}\n{css}\n{js}"
    if _URL_RE.search(combined):
        raise ValueError("Gadget output contains a URL; must be offline/self-contained.")
    if _FORBIDDEN_HTML_RE.search(html):
        raise ValueError("Gadget HTML contains forbidden tags (<script>/<style>/<link>/etc.).")
    if _FORBIDDEN_JS_RE.search(js):
        raise ValueError("Gadget JS appears to use network or dynamic import APIs.")


def generate_one(
    client: OpenAI,
    *,
    model: str,
    ref: str,
    greek_text: str,
    english_translation: str,
) -> tuple[str, str, str, int]:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": USER_PROMPT.format(
                    ref=ref, greek_text=greek_text, english_translation=english_translation
                ),
            },
        ],
        tools=[GADGET_TOOL],
        tool_choice={"type": "function", "function": {"name": "generate_gadget"}},
        temperature=0.2,
    )

    tool_call = response.choices[0].message.tool_calls[0]
    result = json.loads(tool_call.function.arguments)
    html = (result.get("html") or "").strip()
    css = (result.get("css") or "").strip()
    js = (result.get("js") or "").strip()
    if not html or not js:
        raise ValueError("Empty gadget output returned by model/tool.")

    _validate_gadget(html=html, css=css, js=js)

    tokens_used = response.usage.total_tokens if response.usage else 0
    return html, css, js, tokens_used


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate one (or a few) small HTML/CSS/JS gadgets for Herodian passages."
    )
    parser.add_argument("--limit", type=int, default=1, help="Max gadgets to generate (default: 1)")
    parser.add_argument("--model", default="gpt-5.2", help="OpenAI model name (default: gpt-5.2)")
    parser.add_argument("--delay", type=float, default=0.0, help="Delay between requests in seconds")
    args = parser.parse_args()

    if args.limit <= 0:
        print("Gadget generation skipped (limit <= 0).")
        return

    model = _load_model(args.model)
    api_key = load_openai_api_key()
    client = OpenAI(api_key=api_key)

    conn = get_connection()
    total_tokens = 0
    generated = 0
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, ref, greek_text, english_translation
                    FROM cathpros_lines
                    WHERE gadget_html IS NULL
                      AND english_translation IS NOT NULL
                      AND greek_text IS NOT NULL
                      AND ref NOT IN ('E')
                      AND COALESCE(ref_major, 1) <> 0
                    ORDER BY gadget_attempts ASC, gadget_last_attempted_at ASC NULLS FIRST, ref_major NULLS LAST, ref_minor NULLS LAST, ref
                    LIMIT %s
                    FOR UPDATE SKIP LOCKED
                    """,
                    (args.limit,),
                )
                rows = cur.fetchall()

                if not rows:
                    print("No lines pending gadget.")
                    return

                for line_id, ref, greek_text, english_translation in rows:
                    now = datetime.now(timezone.utc)
                    try:
                        html, css, js, tokens_used = generate_one(
                            client,
                            model=model,
                            ref=ref,
                            greek_text=greek_text,
                            english_translation=english_translation,
                        )
                        total_tokens += tokens_used
                        cur.execute(
                            """
                            UPDATE cathpros_lines
                            SET gadget_html = %s,
                                gadget_css = %s,
                                gadget_js = %s,
                                gadget_generated_at = %s,
                                gadget_model = %s,
                                gadget_tokens = %s,
                                gadget_error = NULL,
                                gadget_last_attempted_at = %s,
                                gadget_attempts = gadget_attempts + 1
                            WHERE id = %s
                            """,
                            (html, css, js, now, model, tokens_used, now, line_id),
                        )
                        generated += 1
                        print(f"Generated gadget for {ref} (id={line_id}, tokens={tokens_used}).")
                    except Exception as e:  # noqa: BLE001 - keep pipeline running
                        cur.execute(
                            """
                            UPDATE cathpros_lines
                            SET gadget_error = %s,
                                gadget_last_attempted_at = %s,
                                gadget_attempts = gadget_attempts + 1
                            WHERE id = %s
                            """,
                            (repr(e), now, line_id),
                        )
                        print(f"FAILED gadget {ref} (id={line_id}): {e}")

                    if args.delay and args.delay > 0:
                        time.sleep(args.delay)
    finally:
        conn.close()

    print(f"OK: generated {generated} gadgets (total_tokens={total_tokens}).")


if __name__ == "__main__":
    main()
