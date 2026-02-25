#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path


P_PAREN_RE = re.compile(r"\s*\([^)]*p\.[^)]*\)\s*")
MULTISPACE_RE = re.compile(r"[ \t]{2,}")
SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([,.;:·])")


def strip_editorial_page_parens(text: str) -> tuple[str, int]:
    """
    Remove parenthetical editorial page refs like "(p. 630)" and
    bibliography-style parentheticals containing "p.".

    Returns (cleaned_text, removed_count).
    """
    removed = 0

    def _sub(_m: re.Match) -> str:
        nonlocal removed
        removed += 1
        return " "

    out = P_PAREN_RE.sub(_sub, text)
    out = MULTISPACE_RE.sub(" ", out)
    out = SPACE_BEFORE_PUNCT_RE.sub(r"\1", out)
    out = out.strip()
    return out, removed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Strip editorial parenthetical page refs (p. NNN) from Herodian TSV greek_text."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default="HerodianCathPros.txt",
        help="Path to HerodianCathPros.txt (default: ./HerodianCathPros.txt)",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Rewrite the file in place (atomic). If omitted, print cleaned TSV to stdout.",
    )
    args = parser.parse_args()

    in_path = Path(args.path)
    if not in_path.exists():
        raise FileNotFoundError(f"Input not found: {in_path}")

    removed_total = 0
    changed_lines = 0
    out_lines: list[str] = []

    with in_path.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            raw = line.rstrip("\n")
            parts = raw.split("\t")
            if len(parts) != 5:
                raise ValueError(f"{in_path}:{line_num}: expected 5 TSV fields, got {len(parts)}")
            greek_text = parts[4]
            cleaned, removed = strip_editorial_page_parens(greek_text)
            removed_total += removed
            if cleaned != greek_text:
                changed_lines += 1
                parts[4] = cleaned
            out_lines.append("\t".join(parts) + "\n")

    if args.in_place:
        tmp_path = in_path.with_suffix(in_path.suffix + ".tmp")
        tmp_path.write_text("".join(out_lines), encoding="utf-8")
        tmp_path.replace(in_path)
        print(f"OK: updated {in_path} ({changed_lines} lines changed; {removed_total} parentheticals removed).")
    else:
        for l in out_lines:
            print(l, end="")


if __name__ == "__main__":
    main()

