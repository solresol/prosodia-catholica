#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import unicodedata
import zlib
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher

from psycopg2.extras import execute_values

from db import get_connection as get_herodian_connection
from stephanos_db import get_connection as get_stephanos_connection


GREEK_WORD_RE = re.compile(r"[\u0370-\u03FF\u1F00-\u1FFF]+", flags=re.UNICODE)


def strip_diacritics(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text or "")
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize_greek_letters(text: str) -> str:
    base = strip_diacritics(text).lower().replace("ς", "σ")
    out = []
    for ch in base:
        o = ord(ch)
        if (0x0370 <= o <= 0x03FF) or (0x1F00 <= o <= 0x1FFF):
            if ch.isalpha():
                out.append(ch)
    return "".join(out)


def normalize_greek_words(text: str) -> list[str]:
    base = strip_diacritics(text).lower().replace("ς", "σ")
    return GREEK_WORD_RE.findall(base)


def crc32_u32(value: str) -> int:
    return zlib.crc32(value.encode("utf-8")) & 0xFFFFFFFF


def char_shingles(text: str, k: int) -> set[int]:
    if not text or k <= 0 or len(text) < k:
        return set()
    return {crc32_u32(text[i : i + k]) for i in range(0, len(text) - k + 1)}


def word_shingles(words: list[str], k: int) -> set[int]:
    if not words or k <= 0 or len(words) < k:
        return set()
    out: set[int] = set()
    for i in range(0, len(words) - k + 1):
        out.add(crc32_u32(" ".join(words[i : i + k])))
    return out


def longest_common_block_len(a, b) -> int:
    if not a or not b:
        return 0
    match = SequenceMatcher(None, a, b, autojunk=False).find_longest_match(
        0, len(a), 0, len(b)
    )
    return match.size


@dataclass(frozen=True)
class StephanosEntry:
    lemma_id: int
    headword: str | None
    meineke_id: str | None
    text_body: str
    norm_letters: str
    norm_words: list[str]


def fetch_stephanos_entries() -> list[StephanosEntry]:
    conn = get_stephanos_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT l.id, l.lemma, l.meineke_id, v.text_body
                FROM assembled_lemmas l
                JOIN lemma_source_text_versions v
                  ON v.lemma_id = l.id
                WHERE v.source_document = 'meineke'
                  AND v.is_current = TRUE
                  AND v.text_body IS NOT NULL
                ORDER BY l.id
                """
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    entries: list[StephanosEntry] = []
    for lemma_id, headword, meineke_id, text_body in rows:
        norm_letters = normalize_greek_letters(text_body)
        norm_words = normalize_greek_words(text_body)
        entries.append(
            StephanosEntry(
                lemma_id=int(lemma_id),
                headword=headword,
                meineke_id=meineke_id,
                text_body=text_body,
                norm_letters=norm_letters,
                norm_words=norm_words,
            )
        )
    return entries


def fetch_herodian_lines(limit: int | None) -> list[tuple[int, str, str]]:
    conn = get_herodian_connection()
    try:
        with conn.cursor() as cur:
            query = """
                SELECT id, ref, greek_text
                FROM cathpros_lines
                WHERE greek_text IS NOT NULL
                  AND ref NOT IN ('E')
                ORDER BY ref_major NULLS LAST, ref_minor NULLS LAST, ref
            """
            if limit is not None:
                query += " LIMIT %s"
                cur.execute(query, (int(limit),))
            else:
                cur.execute(query)
            rows = cur.fetchall()
    finally:
        conn.close()
    return [(int(i), str(r), str(t)) for (i, r, t) in rows]


def build_inverted_indexes(
    entries: list[StephanosEntry], *, char_k: int, word_k: int
) -> tuple[dict[int, list[int]], dict[int, list[int]]]:
    char_index: dict[int, list[int]] = defaultdict(list)
    word_index: dict[int, list[int]] = defaultdict(list)

    for e in entries:
        for sh in char_shingles(e.norm_letters, char_k):
            char_index[sh].append(e.lemma_id)
        for sh in word_shingles(e.norm_words, word_k):
            word_index[sh].append(e.lemma_id)

    return dict(char_index), dict(word_index)


def compute_best_matches_for_line(
    *,
    line_text: str,
    entries_by_id: dict[int, StephanosEntry],
    char_index: dict[int, list[int]],
    word_index: dict[int, list[int]],
    char_k: int,
    word_k: int,
    candidate_limit: int,
    max_matches: int,
    min_char_lcs: int,
    min_word_lcs: int,
) -> list[dict]:
    line_letters = normalize_greek_letters(line_text)
    line_words = normalize_greek_words(line_text)

    line_char_sh = char_shingles(line_letters, char_k)
    line_word_sh = word_shingles(line_words, word_k)

    char_hits: Counter[int] = Counter()
    word_hits: Counter[int] = Counter()
    for sh in line_char_sh:
        for lemma_id in char_index.get(sh, ()):
            char_hits[lemma_id] += 1
    for sh in line_word_sh:
        for lemma_id in word_index.get(sh, ()):
            word_hits[lemma_id] += 1

    combined: Counter[int] = Counter()
    for lemma_id, n in char_hits.items():
        combined[lemma_id] += n
    for lemma_id, n in word_hits.items():
        combined[lemma_id] += n * 5  # word shingles are higher-signal

    candidates = [lemma_id for lemma_id, _ in combined.most_common(candidate_limit)]
    if not candidates:
        return []

    scored = []
    for lemma_id in candidates:
        entry = entries_by_id.get(lemma_id)
        if not entry:
            continue

        char_lcs = longest_common_block_len(line_letters, entry.norm_letters)
        word_lcs = longest_common_block_len(line_words, entry.norm_words)

        if char_lcs < min_char_lcs and word_lcs < min_word_lcs:
            continue

        char_ratio = char_lcs / max(1, min(len(line_letters), len(entry.norm_letters)))
        word_ratio = word_lcs / max(1, min(len(line_words), len(entry.norm_words)))

        scored.append(
            {
                "stephanos_lemma_id": lemma_id,
                "stephanos_meineke_id": entry.meineke_id,
                "stephanos_headword": entry.headword,
                "char_lcs_len": int(char_lcs),
                "char_lcs_ratio": float(char_ratio),
                "word_lcs_len": int(word_lcs),
                "word_lcs_ratio": float(word_ratio),
                "shared_char_shingles": int(char_hits.get(lemma_id, 0)),
                "shared_word_shingles": int(word_hits.get(lemma_id, 0)),
            }
        )

    scored.sort(
        key=lambda d: (
            d["char_lcs_ratio"],
            d["word_lcs_ratio"],
            d["char_lcs_len"],
            d["word_lcs_len"],
            d["shared_word_shingles"],
            d["shared_char_shingles"],
        ),
        reverse=True,
    )
    return scored[:max_matches]


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute overlaps between Herodian and Stephanos Meineke texts.")
    parser.add_argument("--metric-version", default="v1", help="Metric/version label (default: v1)")
    parser.add_argument("--limit-lines", type=int, help="Only process first N Herodian lines")
    parser.add_argument("--max-matches", type=int, default=10, help="Keep top N matches per Herodian line (default: 10)")
    parser.add_argument("--candidate-limit", type=int, default=250, help="Max candidates to score per line (default: 250)")
    parser.add_argument("--char-shingle", type=int, default=36, help="Character shingle length (default: 36)")
    parser.add_argument("--word-shingle", type=int, default=5, help="Word shingle length (default: 5)")
    parser.add_argument("--min-char-lcs", type=int, default=30, help="Min char LCS to keep a match (default: 30)")
    parser.add_argument("--min-word-lcs", type=int, default=4, help="Min word LCS to keep a match (default: 4)")
    args = parser.parse_args()

    stephanos_entries = fetch_stephanos_entries()
    entries_by_id = {e.lemma_id: e for e in stephanos_entries}

    char_index, word_index = build_inverted_indexes(
        stephanos_entries, char_k=args.char_shingle, word_k=args.word_shingle
    )

    herodian_lines = fetch_herodian_lines(args.limit_lines)

    now = datetime.now(timezone.utc)
    her_conn = get_herodian_connection()
    try:
        with her_conn:
            with her_conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO stephanos_overlap_runs
                      (metric_version, created_at, stephanos_lemmas_count, stephanos_meineke_current_count)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        args.metric_version,
                        now,
                        len(stephanos_entries),
                        len(stephanos_entries),
                    ),
                )
                (run_id,) = cur.fetchone()

                rows_to_insert = []
                for idx, (line_id, ref, greek_text) in enumerate(herodian_lines, 1):
                    matches = compute_best_matches_for_line(
                        line_text=greek_text,
                        entries_by_id=entries_by_id,
                        char_index=char_index,
                        word_index=word_index,
                        char_k=args.char_shingle,
                        word_k=args.word_shingle,
                        candidate_limit=args.candidate_limit,
                        max_matches=args.max_matches,
                        min_char_lcs=args.min_char_lcs,
                        min_word_lcs=args.min_word_lcs,
                    )

                    for m in matches:
                        rows_to_insert.append(
                            (
                                int(run_id),
                                int(line_id),
                                int(m["stephanos_lemma_id"]),
                                m["stephanos_meineke_id"],
                                m["stephanos_headword"],
                                int(m["char_lcs_len"]),
                                float(m["char_lcs_ratio"]),
                                int(m["word_lcs_len"]),
                                float(m["word_lcs_ratio"]),
                                int(m["shared_char_shingles"]),
                                int(m["shared_word_shingles"]),
                            )
                        )

                    if idx % 25 == 0 or idx == len(herodian_lines):
                        print(f"Scored {idx}/{len(herodian_lines)} Herodian lines…")

                if rows_to_insert:
                    execute_values(
                        cur,
                        """
                        INSERT INTO stephanos_overlap_matches
                          (run_id, herodian_line_id, stephanos_lemma_id, stephanos_meineke_id, stephanos_headword,
                           char_lcs_len, char_lcs_ratio, word_lcs_len, word_lcs_ratio,
                           shared_char_shingles, shared_word_shingles)
                        VALUES %s
                        """,
                        rows_to_insert,
                        page_size=5000,
                    )

                cur.execute(
                    "UPDATE stephanos_overlap_runs SET finished_at = %s WHERE id = %s",
                    (datetime.now(timezone.utc), run_id),
                )

    finally:
        her_conn.close()

    print(f"OK: overlap run complete (run_id={run_id}, matches={len(rows_to_insert)}).")


if __name__ == "__main__":
    main()

