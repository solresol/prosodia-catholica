#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone

from openai import OpenAI

from db import get_connection
from openai_utils import load_openai_api_key


SYSTEM_PROMPT = (
    "You are a classical philologist. Translate Greek technical prose accurately into clear English. "
    "Preserve grammatical terminology and do not add commentary beyond the translation."
)

USER_PROMPT = """Translate the following text from Aelius Herodianus (Περὶ καθολικῆς προσῳδίας) into English.

Rules:
- Output only the English translation (no preface, no notes).
- Keep any Greek words in Greek script when they are cited as examples.
- Preserve citations like (Il. 13, 1) verbatim.

Greek text:
{greek_text}
"""


TRANSLATE_TOOL = {
    "type": "function",
    "function": {
        "name": "translate_line",
        "description": "Translate one Greek passage into English.",
        "parameters": {
            "type": "object",
            "properties": {
                "english_translation": {"type": "string"},
            },
            "required": ["english_translation"],
        },
    },
}


def _load_model(default: str) -> str:
    try:
        from config import OPENAI_MODEL as CONFIG_OPENAI_MODEL
    except ImportError:
        CONFIG_OPENAI_MODEL = None
    return (CONFIG_OPENAI_MODEL or default).strip()


def translate_one(client: OpenAI, *, model: str, greek_text: str) -> tuple[str, int]:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT.format(greek_text=greek_text)},
        ],
        tools=[TRANSLATE_TOOL],
        tool_choice={"type": "function", "function": {"name": "translate_line"}},
        temperature=0.2,
    )

    tool_call = response.choices[0].message.tool_calls[0]
    result = json.loads(tool_call.function.arguments)
    translation = (result.get("english_translation") or "").strip()
    if not translation:
        raise ValueError("Empty translation returned by model/tool.")

    tokens_used = response.usage.total_tokens if response.usage else 0
    return translation, tokens_used


def main() -> None:
    parser = argparse.ArgumentParser(description="Translate a few more Herodian lines into English.")
    parser.add_argument("--limit", type=int, default=5, help="Max lines to translate (default: 5)")
    parser.add_argument("--model", default="gpt-5.2", help="OpenAI model name (default: gpt-5.2)")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between requests in seconds")
    args = parser.parse_args()

    model = _load_model(args.model)
    api_key = load_openai_api_key()
    client = OpenAI(api_key=api_key)

    conn = get_connection()
    total_tokens = 0
    translated = 0
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, ref, greek_text
                    FROM cathpros_lines
                    WHERE english_translation IS NULL
                      AND greek_text IS NOT NULL
                      AND ref NOT IN ('E')
                      AND COALESCE(ref_major, 1) <> 0
                    ORDER BY ref_major NULLS LAST, ref_minor NULLS LAST, ref
                    LIMIT %s
                    FOR UPDATE SKIP LOCKED
                    """,
                    (args.limit,),
                )
                to_translate = cur.fetchall()

                if not to_translate:
                    print("No lines pending translation.")
                    return

                for line_id, ref, greek_text in to_translate:
                    now = datetime.now(timezone.utc)
                    try:
                        english, tokens_used = translate_one(
                            client, model=model, greek_text=greek_text
                        )
                        total_tokens += tokens_used
                        cur.execute(
                            """
                            UPDATE cathpros_lines
                            SET english_translation = %s,
                                translated_at = %s,
                                translation_model = %s,
                                translation_tokens = %s,
                                translation_error = NULL,
                                last_attempted_at = %s,
                                translation_attempts = translation_attempts + 1
                            WHERE id = %s
                            """,
                            (english, now, model, tokens_used, now, line_id),
                        )
                        translated += 1
                        print(f"Translated {ref} (id={line_id}, tokens={tokens_used}).")
                    except Exception as e:  # noqa: BLE001 - keep pipeline running
                        cur.execute(
                            """
                            UPDATE cathpros_lines
                            SET translation_error = %s,
                                last_attempted_at = %s,
                                translation_attempts = translation_attempts + 1
                            WHERE id = %s
                            """,
                            (repr(e), now, line_id),
                        )
                        print(f"FAILED {ref} (id={line_id}): {e}")

                    if args.delay and args.delay > 0:
                        time.sleep(args.delay)
    finally:
        conn.close()

    print(f"OK: translated {translated} lines (total_tokens={total_tokens}).")


if __name__ == "__main__":
    main()

