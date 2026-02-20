#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from db import get_connection


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
.pill{
  display:inline-block;
  padding:3px 10px;
  border-radius:999px;
  border:1px solid var(--border);
  color:var(--muted);
  font-size:12px;
}
.lines{margin-top:18px;display:flex;flex-direction:column;gap:12px;}
.line{
  border:1px solid var(--border);
  background:rgba(17,26,51,.55);
  border-radius:14px;
  padding:14px 14px 12px;
}
.line-head{display:flex;gap:10px;align-items:center;justify-content:space-between;flex-wrap:wrap;}
.ref{font-weight:650;}
.ts{color:var(--muted);font-size:12px;}
.grid{display:grid;grid-template-columns:1fr;gap:10px;margin-top:10px;}
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
footer{margin-top:26px;color:var(--muted);font-size:13px;}
"""


def render_index(*, title: str, stats: dict, lines: list[dict]) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    translated = stats["translated"]
    total = stats["total"]
    percent = (translated / total * 100.0) if total else 0.0
    percent_str = f"{percent:.1f}%"

    items_html = []
    for row in lines:
        ref = row["ref"]
        greek = row["greek_text"] or ""
        english = row["english_translation"]
        translated_at = row["translated_at"]
        ts = ""
        if translated_at:
            ts = escape(translated_at.strftime("%Y-%m-%d"))
        items_html.append(
            f"""
            <section class="line" id="ref-{escape(ref)}">
              <div class="line-head">
                <div class="ref"><a href="#ref-{escape(ref)}">{escape(ref)}</a></div>
                <div class="ts">{ts}</div>
              </div>
              <div class="grid">
                <div class="greek" lang="el">{escape(greek)}</div>
                <div class="english">{escape(english) if english else '<span class="pending">Pending translation</span>'}</div>
              </div>
            </section>
            """.strip()
        )

    items = "\n".join(items_html)
    stats_json = escape(json.dumps(stats, ensure_ascii=False))

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
    <header>
      <h1>{escape(title)}</h1>
      <div class="meta"><span class="pill">{translated}/{total} translated</span> <span class="pill">{percent_str}</span></div>
    </header>
    <div class="controls">
      <input id="q" type="search" placeholder="Filter by ref or text…" autocomplete="off" />
      <span class="pill">Generated: {escape(generated_at)}</span>
    </div>
    <div class="lines" id="lines">
      {items}
    </div>
    <footer>
      <div>Stats: <code id="stats">{stats_json}</code></div>
    </footer>
  </div>
  <script>
    const q = document.getElementById('q');
    const lines = Array.from(document.querySelectorAll('.line'));
    function norm(s){{ return (s||'').toLowerCase(); }}
    function apply(){{
      const needle = norm(q.value).trim();
      for (const el of lines){{
        if (!needle){{ el.style.display = ''; continue; }}
        const hay = norm(el.innerText);
        el.style.display = hay.includes(needle) ? '' : 'none';
      }}
    }}
    q.addEventListener('input', apply);
  </script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate static site from cathpros_lines.")
    parser.add_argument("--out", default="site", help="Output directory (default: site)")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    conn = get_connection(dict_cursor=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT ref, greek_text, english_translation, translated_at
                FROM cathpros_lines
                ORDER BY ref_major NULLS LAST, ref_minor NULLS LAST, ref
                """
            )
            rows = cur.fetchall()

            cur.execute(
                """
                SELECT
                  COUNT(*) FILTER (WHERE ref NOT IN ('E') AND COALESCE(ref_major, 1) <> 0) AS total,
                  COUNT(*) FILTER (WHERE english_translation IS NOT NULL AND ref NOT IN ('E') AND COALESCE(ref_major, 1) <> 0) AS translated
                FROM cathpros_lines
                """
            )
            stats_row = cur.fetchone()
    finally:
        conn.close()

    lines = []
    for r in rows:
        lines.append(
            {
                "ref": r["ref"],
                "greek_text": r["greek_text"],
                "english_translation": r["english_translation"],
                "translated_at": r["translated_at"],
            }
        )

    stats = {
        "total": int(stats_row["total"] or 0),
        "translated": int(stats_row["translated"] or 0),
    }

    (out_dir / "style.css").write_text(STYLE_CSS.strip() + "\n", encoding="utf-8")
    json_lines = []
    for row in lines:
        json_lines.append(
            {
                **row,
                "translated_at": row["translated_at"].isoformat()
                if row["translated_at"]
                else None,
            }
        )
    (out_dir / "lines.json").write_text(
        json.dumps(json_lines, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "index.html").write_text(
        render_index(title=_site_title("Prosodia Catholica (Herodian)"), stats=stats, lines=lines),
        encoding="utf-8",
    )

    print(f"OK: wrote {out_dir}/index.html ({len(lines)} lines).")


if __name__ == "__main__":
    main()
