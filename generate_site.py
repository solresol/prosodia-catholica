#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from db import get_connection
from stephanos_db import get_connection as get_stephanos_connection


def _site_title(default: str) -> str:
    try:
        from config import SITE_TITLE as CONFIG_SITE_TITLE
    except ImportError:
        CONFIG_SITE_TITLE = None
    return (CONFIG_SITE_TITLE or default).strip()


STYLE_CSS = """
:root{
  --bg:#0b1020;
  --panel:#111a33;
  --text:#e7ecff;
  --muted:#aab4e6;
  --accent:#7aa2ff;
  --border:#243059;
}
html,body{height:100%;}
body{
  margin:0;
  background:linear-gradient(180deg,var(--bg),#070a14);
  color:var(--text);
  font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, "Apple Color Emoji","Segoe UI Emoji";
}
a{color:var(--accent); text-decoration:none;}
a:hover{text-decoration:underline;}
.wrap{max-width:1100px;margin:0 auto;padding:28px 18px 64px;}
header{display:flex;gap:16px;align-items:baseline;flex-wrap:wrap;}
h1{font-size:28px;margin:0;}
.meta{color:var(--muted);font-size:14px;}
.controls{margin-top:14px;display:flex;gap:10px;flex-wrap:wrap;}
input[type="search"]{
  flex:1 1 320px;
  padding:10px 12px;
  border-radius:10px;
  border:1px solid var(--border);
  background:rgba(17,26,51,.65);
  color:var(--text);
  outline:none;
}
.btn{
  display:inline-flex;
  align-items:center;
  gap:8px;
  padding:9px 12px;
  border-radius:10px;
  border:1px solid var(--border);
  background:rgba(17,26,51,.55);
  color:var(--text);
}
.pill{
  display:inline-block;
  padding:3px 10px;
  border-radius:999px;
  border:1px solid var(--border);
  color:var(--muted);
  font-size:12px;
}
.list{margin-top:18px;display:flex;flex-direction:column;gap:10px;}
.row{
  border:1px solid var(--border);
  background:rgba(17,26,51,.55);
  border-radius:14px;
  padding:12px 14px 11px;
}
.row-head{display:flex;gap:10px;align-items:center;justify-content:space-between;flex-wrap:wrap;}
.ref{font-weight:650; font-size:16px;}
.summary{color:var(--muted); font-size:14px; margin-top:6px;}
.kvs{display:flex;gap:8px;flex-wrap:wrap; align-items:center;}
.kv{color:var(--muted); font-size:12px; border:1px solid var(--border); border-radius:999px; padding:2px 10px;}
.ts{color:var(--muted);font-size:12px;}
.grid{display:grid;grid-template-columns:1fr;gap:10px;margin-top:14px;}
@media (min-width: 880px){
  .grid{grid-template-columns:1fr 1fr;}
}
.greek{
  font-family: ui-serif, "New Athena Unicode", "Palatino Linotype", Palatino, serif;
  font-size:16px;
  line-height:1.55;
  white-space:pre-wrap;
}
.english{
  font-size:15px;
  line-height:1.55;
  white-space:pre-wrap;
}
.pending{color:var(--muted);font-style:italic;}
details{margin-top:10px;}
details summary{cursor:pointer; color:var(--accent);}
pre{
  background:rgba(17,26,51,.45);
  border:1px solid var(--border);
  border-radius:12px;
  padding:12px;
  overflow:auto;
  white-space:pre-wrap;
}
footer{margin-top:26px;color:var(--muted);font-size:13px;}
"""

_SAFE_REF_RE = re.compile(r"[^0-9A-Za-z._-]+")


def ref_to_slug(ref: str) -> str:
    slug = ref.strip()
    slug = slug.replace("/", "_").replace(" ", "_")
    slug = _SAFE_REF_RE.sub("_", slug)
    return slug or "ref"


def render_shell(*, title: str, body_html: str) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>{escape(title)}</title>
  <link rel="stylesheet" href="style.css" />
</head>
<body>
  <div class="wrap">
    {body_html}
    <footer>Generated: {escape(generated_at)}</footer>
  </div>
</body>
</html>
"""


def render_index(*, title: str, stats: dict, lines: list[dict], top_overlap_by_line: dict[int, dict]) -> str:
    translated = stats["translated"]
    summarized = stats["summarized"]
    total = stats["total"]
    percent = (translated / total * 100.0) if total else 0.0
    percent_str = f"{percent:.1f}%"

    items_html = []
    for row in lines:
        line_id = row["id"]
        ref = row["ref"]
        slug = ref_to_slug(ref)
        summary = row.get("summary") or ""
        overlap = top_overlap_by_line.get(line_id)
        overlap_label = ""
        if overlap and overlap.get("stephanos_meineke_id"):
            overlap_label = escape(str(overlap["stephanos_meineke_id"]))
        overlap_kv_html = (
            f"<span class='kv'>top overlap: {overlap_label}</span>" if overlap_label else ""
        )
        status_bits = []
        if row.get("english_translation"):
            status_bits.append("translated")
        else:
            status_bits.append("pending translation")
        if row.get("summary"):
            status_bits.append("summarized")
        else:
            status_bits.append("pending summary")

        items_html.append(
            f"""
            <section class="row" data-hay="{escape(ref + ' ' + summary)}">
              <div class="row-head">
                <div>
                  <div class="ref"><a href="passages/{escape(slug)}.html">{escape(ref)}</a></div>
                  <div class="summary">{escape(summary) if summary else '<span class="pending">No summary yet</span>'}</div>
                </div>
                <div class="kvs">
                  <span class="kv">{escape(', '.join(status_bits))}</span>
                  {overlap_kv_html}
                </div>
              </div>
            </section>
            """.strip()
        )

    items = "\n".join(items_html)
    stats_json = escape(json.dumps(stats, ensure_ascii=False))

    body = f"""
    <header>
      <h1>{escape(title)}</h1>
      <div class="meta">
        <span class="pill">{translated}/{total} translated</span>
        <span class="pill">{summarized}/{total} summarized</span>
        <span class="pill">{percent_str}</span>
      </div>
    </header>
    <div class="controls">
      <input id="q" type="search" placeholder="Filter by ref or summary…" autocomplete="off" />
      <a class="btn" href="index.html">Index</a>
    </div>
    <div class="list" id="rows">
      {items}
    </div>
    <div class="meta">Stats: <code id="stats">{stats_json}</code></div>
    <script>
      const q = document.getElementById('q');
      const rows = Array.from(document.querySelectorAll('.row'));
      function norm(s){{ return (s||'').toLowerCase(); }}
      function apply(){{
        const needle = norm(q.value).trim();
        for (const el of rows){{
          if (!needle){{ el.style.display = ''; continue; }}
          const hay = norm(el.getAttribute('data-hay') || el.innerText);
          el.style.display = hay.includes(needle) ? '' : 'none';
        }}
      }}
      q.addEventListener('input', apply);
    </script>
    """.strip()

    return render_shell(title=title, body_html=body)


def render_passage(
    *,
    site_title: str,
    ref: str,
    summary: str | None,
    greek_text: str,
    english_translation: str | None,
    overlaps: list[dict],
    stephanos_text_by_lemma_id: dict[int, dict],
) -> str:
    title = f"{site_title} — {ref}"
    overlaps_html = []
    for ov in overlaps:
        lemma_id = int(ov["stephanos_lemma_id"])
        meineke_id = ov.get("stephanos_meineke_id") or ""
        headword = ov.get("stephanos_headword") or ""
        char_pct = f"{ov['char_lcs_ratio']*100:.1f}%"
        word_pct = f"{ov['word_lcs_ratio']*100:.1f}%"
        stephanos_text = stephanos_text_by_lemma_id.get(lemma_id, {}).get("text_body")

        overlaps_html.append(
            f"""
            <div class="row">
              <div class="row-head">
                <div class="ref">{escape(meineke_id) if meineke_id else f'lemma {lemma_id}'} {escape(headword)}</div>
                <div class="kvs">
                  <span class="kv">char LCS {escape(str(ov['char_lcs_len']))} ({escape(char_pct)})</span>
                  <span class="kv">word LCS {escape(str(ov['word_lcs_len']))} ({escape(word_pct)})</span>
                </div>
              </div>
              {f'<details><summary>Stephanos text</summary><pre>{escape(stephanos_text)}</pre></details>' if stephanos_text else ''}
            </div>
            """.strip()
        )

    overlaps_block = (
        "<div class='meta'><span class='pending'>No overlaps computed yet.</span></div>"
        if not overlaps_html
        else "\n".join(overlaps_html)
    )

    body = f"""
    <header>
      <h1><a href="../index.html">{escape(site_title)}</a></h1>
      <div class="meta"><span class="pill">Passage {escape(ref)}</span></div>
    </header>
    <div class="controls">
      <a class="btn" href="../index.html">← Index</a>
    </div>
    <div class="row">
      <div class="ref">{escape(ref)}</div>
      <div class="summary">{escape(summary) if summary else '<span class="pending">No summary yet</span>'}</div>
      <div class="grid">
        <div class="greek" lang="el">{escape(greek_text or '')}</div>
        <div class="english">{escape(english_translation) if english_translation else '<span class="pending">Pending translation</span>'}</div>
      </div>
    </div>
    <h2>Overlaps (Stephanos, Meineke)</h2>
    {overlaps_block}
    """.strip()

    return render_shell(title=title, body_html=body)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate static site from cathpros_lines.")
    parser.add_argument("--out", default="site", help="Output directory (default: site)")
    parser.add_argument("--overlap-metric-version", default="v1", help="Overlap metric version to display (default: v1)")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    passages_dir = out_dir / "passages"
    passages_dir.mkdir(parents=True, exist_ok=True)

    conn = get_connection(dict_cursor=True)
    latest_run_id = None
    overlap_rows = []
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, ref, greek_text, english_translation, summary, translated_at
                FROM cathpros_lines
                WHERE ref NOT IN ('E')
                ORDER BY ref_major NULLS LAST, ref_minor NULLS LAST, ref
                """
            )
            rows = cur.fetchall()

            cur.execute(
                """
                SELECT
                  COUNT(*) FILTER (WHERE ref NOT IN ('E')) AS total,
                  COUNT(*) FILTER (WHERE english_translation IS NOT NULL AND ref NOT IN ('E') AND COALESCE(ref_major, 1) <> 0) AS translated,
                  COUNT(*) FILTER (WHERE summary IS NOT NULL AND ref NOT IN ('E')) AS summarized
                FROM cathpros_lines
                """
            )
            stats_row = cur.fetchone()

            cur.execute(
                """
                SELECT id
                FROM stephanos_overlap_runs
                WHERE metric_version = %s
                  AND finished_at IS NOT NULL
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (args.overlap_metric_version,),
            )
            run = cur.fetchone()
            if run:
                latest_run_id = int(run["id"])
                cur.execute(
                    """
                    SELECT
                      herodian_line_id,
                      stephanos_lemma_id,
                      stephanos_meineke_id,
                      stephanos_headword,
                      char_lcs_len,
                      char_lcs_ratio,
                      word_lcs_len,
                      word_lcs_ratio,
                      shared_char_shingles,
                      shared_word_shingles
                    FROM stephanos_overlap_matches
                    WHERE run_id = %s
                    ORDER BY herodian_line_id, char_lcs_ratio DESC, word_lcs_ratio DESC, char_lcs_len DESC
                    """,
                    (latest_run_id,),
                )
                overlap_rows = cur.fetchall()
    finally:
        conn.close()

    lines = []
    for r in rows:
        lines.append(
            {
                "id": int(r["id"]),
                "ref": r["ref"],
                "greek_text": r["greek_text"],
                "english_translation": r["english_translation"],
                "summary": r.get("summary"),
                "translated_at": r["translated_at"],
            }
        )

    stats = {
        "total": int(stats_row["total"] or 0),
        "translated": int(stats_row["translated"] or 0),
        "summarized": int(stats_row["summarized"] or 0),
        "latest_overlap_run_id": latest_run_id,
    }

    (out_dir / "style.css").write_text(STYLE_CSS.strip() + "\n", encoding="utf-8")

    overlaps_by_line: dict[int, list[dict]] = {}
    for ov in overlap_rows:
        overlaps_by_line.setdefault(int(ov["herodian_line_id"]), []).append(
            {
                "stephanos_lemma_id": int(ov["stephanos_lemma_id"]),
                "stephanos_meineke_id": ov.get("stephanos_meineke_id"),
                "stephanos_headword": ov.get("stephanos_headword"),
                "char_lcs_len": int(ov["char_lcs_len"]),
                "char_lcs_ratio": float(ov["char_lcs_ratio"]),
                "word_lcs_len": int(ov["word_lcs_len"]),
                "word_lcs_ratio": float(ov["word_lcs_ratio"]),
            }
        )

    top_overlap_by_line: dict[int, dict] = {}
    for line_id, ovs in overlaps_by_line.items():
        if ovs:
            top_overlap_by_line[line_id] = ovs[0]

    # Fetch Stephanos texts for the overlap candidates we will show.
    stephanos_text_by_lemma_id: dict[int, dict] = {}
    lemma_ids = sorted({ov["stephanos_lemma_id"] for ovs in overlaps_by_line.values() for ov in ovs[:5]})
    if lemma_ids:
        try:
            sconn = get_stephanos_connection(dict_cursor=True)
            try:
                with sconn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT l.id AS lemma_id, l.lemma AS headword, l.meineke_id, v.text_body
                        FROM assembled_lemmas l
                        JOIN lemma_source_text_versions v ON v.lemma_id = l.id
                        WHERE v.source_document = 'meineke'
                          AND v.is_current = TRUE
                          AND l.id = ANY(%s)
                        """,
                        (lemma_ids,),
                    )
                    for row in cur.fetchall():
                        stephanos_text_by_lemma_id[int(row["lemma_id"])] = {
                            "headword": row.get("headword"),
                            "meineke_id": row.get("meineke_id"),
                            "text_body": row.get("text_body"),
                        }
            finally:
                sconn.close()
        except Exception:
            # If Stephanos DB isn't reachable, just skip embedding text.
            stephanos_text_by_lemma_id = {}

    (out_dir / "passages.json").write_text(
        json.dumps(
            [
                {
                    **row,
                    "translated_at": row["translated_at"].isoformat() if row["translated_at"] else None,
                }
                for row in lines
            ],
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    site_title = _site_title("Prosodia Catholica (Herodian)")
    (out_dir / "index.html").write_text(
        render_index(title=site_title, stats=stats, lines=lines, top_overlap_by_line=top_overlap_by_line),
        encoding="utf-8",
    )

    for row in lines:
        ref = row["ref"]
        slug = ref_to_slug(ref)
        (passages_dir / f"{slug}.html").write_text(
            render_passage(
                site_title=site_title,
                ref=ref,
                summary=row.get("summary"),
                greek_text=row.get("greek_text") or "",
                english_translation=row.get("english_translation"),
                overlaps=(overlaps_by_line.get(row["id"]) or [])[:5],
                stephanos_text_by_lemma_id=stephanos_text_by_lemma_id,
            ),
            encoding="utf-8",
        )

    print(f"OK: wrote {out_dir}/index.html and {len(lines)} passage pages.")


if __name__ == "__main__":
    main()
