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
    "You are a classical philologist. Create a very short English label for an index."
)

USER_PROMPT = """Write a short index label (3–10 words) describing the topic of this passage.

Rules:
- Output only the label (no punctuation-heavy prose, no quotes, no extra lines).
- Prefer concrete keywords (e.g., headword, place/ethnic, accent rule, citation).
- Do not invent details not present in the text.

Greek text:
{greek_text}
"""


SUMMARY_TOOL = {
    "type": "function",
    "function": {
        "name": "summarize_passage",
        "description": "Produce a short index label for a passage.",
        "parameters": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
            },
            "required": ["summary"],
        },
    },
}


def _load_model(default: str) -> str:
    try:
        from config import SUMMARY_MODEL as CONFIG_SUMMARY_MODEL
    except ImportError:
        CONFIG_SUMMARY_MODEL = None
    return (CONFIG_SUMMARY_MODEL or default).strip()


def summarize_one(client: OpenAI, *, model: str, greek_text: str) -> tuple[str, int]:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT.format(greek_text=greek_text)},
        ],
        tools=[SUMMARY_TOOL],
        tool_choice={"type": "function", "function": {"name": "summarize_passage"}},
    )

    tool_call = response.choices[0].message.tool_calls[0]
    result = json.loads(tool_call.function.arguments)
    summary = (result.get("summary") or "").strip()
    if not summary:
        raise ValueError("Empty summary returned by model/tool.")

    tokens_used = response.usage.total_tokens if response.usage else 0
    return summary, tokens_used


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize Herodian lines into short index labels.")
    parser.add_argument("--limit", type=int, default=25, help="Max lines to summarize (default: 25)")
    parser.add_argument("--model", default="gpt-5-mini", help="OpenAI model name (default: gpt-5-mini)")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay between requests in seconds")
    args = parser.parse_args()

    model = _load_model(args.model)
    api_key = load_openai_api_key()
    client = OpenAI(api_key=api_key)

    conn = get_connection()
    total_tokens = 0
    summarized = 0
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, ref, greek_text
                    FROM cathpros_lines
                    WHERE summary IS NULL
                      AND greek_text IS NOT NULL
                      AND ref NOT IN ('E')
                    ORDER BY ref_major NULLS LAST, ref_minor NULLS LAST, ref
                    LIMIT %s
                    FOR UPDATE SKIP LOCKED
                    """,
                    (args.limit,),
                )
                rows = cur.fetchall()

                if not rows:
                    print("No lines pending summary.")
                    return

                for line_id, ref, greek_text in rows:
                    now = datetime.now(timezone.utc)
                    try:
                        summary, tokens_used = summarize_one(
                            client, model=model, greek_text=greek_text
                        )
                        total_tokens += tokens_used
                        cur.execute(
                            """
                            UPDATE cathpros_lines
                            SET summary = %s,
                                summarized_at = %s,
                                summary_model = %s,
                                summary_tokens = %s,
                                summary_error = NULL,
                                summary_last_attempted_at = %s,
                                summary_attempts = summary_attempts + 1
                            WHERE id = %s
                            """,
                            (summary, now, model, tokens_used, now, line_id),
                        )
                        summarized += 1
                        print(f"Summarized {ref} (id={line_id}, tokens={tokens_used}).")
                    except Exception as e:  # noqa: BLE001 - keep pipeline running
                        cur.execute(
                            """
                            UPDATE cathpros_lines
                            SET summary_error = %s,
                                summary_last_attempted_at = %s,
                                summary_attempts = summary_attempts + 1
                            WHERE id = %s
                            """,
                            (repr(e), now, line_id),
                        )
                        print(f"FAILED summary {ref} (id={line_id}): {e}")

                    if args.delay and args.delay > 0:
                        time.sleep(args.delay)
    finally:
        conn.close()

    print(f"OK: summarized {summarized} lines (total_tokens={total_tokens}).")


if __name__ == "__main__":
    main()
