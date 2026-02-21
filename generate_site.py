#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import unicodedata
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
.tag{
  display:inline-block;
  padding:2px 10px;
  border-radius:999px;
  border:1px solid var(--border);
  color:var(--muted);
  font-size:12px;
  margin-right:6px;
}
.tag.ok{border-color:#2c5b3c;background:rgba(44,91,60,.25);color:#c7ffd2;}
.tag.todo{border-color:#5a3b24;background:rgba(90,59,36,.25);color:#ffd9c2;}

.table-wrap{
  margin-top:18px;
  border:1px solid var(--border);
  border-radius:14px;
  overflow:hidden;
  background:rgba(17,26,51,.55);
}
table.tbl{width:100%;border-collapse:separate;border-spacing:0;}
table.tbl thead th{
  position:sticky; top:0; z-index:1;
  text-align:left;
  font-size:12px;
  letter-spacing:.02em;
  color:var(--muted);
  padding:10px 12px;
  border-bottom:1px solid var(--border);
  background:rgba(17,26,51,.92);
}
table.tbl thead th.sortable{cursor:pointer; user-select:none;}
table.tbl thead th.sortable:hover{background:rgba(17,26,51,.98);}
table.tbl thead th .arrow{margin-left:6px; opacity:.7; font-size:11px;}
table.tbl tbody td{
  padding:10px 12px;
  border-bottom:1px solid rgba(36,48,89,.65);
  vertical-align:top;
}
table.tbl tbody tr:hover{background:rgba(17,26,51,.75);}
table.tbl td.ref a{font-weight:650;}
table.tbl td.small{white-space:nowrap;}
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
.hl{padding:0 2px;border-radius:4px;}
.hl-h{background:rgba(255,214,10,.22);}
.hl-s{background:rgba(122,162,255,.22);}
.swatch{
  display:inline-block;
  width:12px;
  height:12px;
  border-radius:4px;
  margin-right:8px;
  vertical-align:-2px;
  border:1px solid rgba(231,236,255,.18);
}
.c0{background:rgba(255,214,10,.22);}
.c1{background:rgba(122,162,255,.22);}
.c2{background:rgba(100,231,173,.20);}
.c3{background:rgba(255,143,171,.20);}
.c4{background:rgba(255,170,0,.20);}
.c5{background:rgba(0,210,255,.18);}
.c6{background:rgba(186,104,200,.20);}
.c7{background:rgba(239,83,80,.18);}
.c8{background:rgba(149,117,205,.20);}
.c9{background:rgba(76,175,80,.18);}
.gadget-frame{
  width:100%;
  height:390px;
  border:1px solid var(--border);
  border-radius:14px;
  background:rgba(17,26,51,.35);
}
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


def _stephanos_base_url(default: str) -> str:
    try:
        from config import STEPHANOS_SITE_BASE_URL as CONFIG_STEPHANOS_SITE_BASE_URL
    except ImportError:
        CONFIG_STEPHANOS_SITE_BASE_URL = None
    return (CONFIG_STEPHANOS_SITE_BASE_URL or default).rstrip("/")


_GREEK_LETTER_SLUG_BY_CHAR = {
    "Α": "alpha",
    "Β": "beta",
    "Γ": "gamma",
    "Δ": "delta",
    "Ε": "epsilon",
    "Ζ": "zeta",
    "Η": "eta",
    "Θ": "theta",
    "Ι": "iota",
    "Κ": "kappa",
    "Λ": "lambda",
    "Μ": "mu",
    "Ν": "nu",
    "Ξ": "xi",
    "Ο": "omicron",
    "Π": "pi",
    "Ρ": "rho",
    "Σ": "sigma",
    "Τ": "tau",
    "Υ": "upsilon",
    "Φ": "phi",
    "Χ": "chi",
    "Ψ": "psi",
    "Ω": "omega",
}


def _strip_combining(ch: str) -> str:
    decomposed = unicodedata.normalize("NFD", ch)
    for c in decomposed:
        if not unicodedata.combining(c):
            return c
    return ch


def stephanos_letter_slug(headword: str | None) -> str | None:
    if not headword:
        return None
    for ch in headword:
        base = _strip_combining(ch).upper()
        slug = _GREEK_LETTER_SLUG_BY_CHAR.get(base)
        if slug:
            return slug
    return None


def stephanos_entry_url(*, base_url: str, lemma_id: int, headword: str | None) -> str:
    slug = stephanos_letter_slug(headword)
    if slug:
        return f"{base_url}/letter_{slug}.html#lemma-{lemma_id}"
    return f"{base_url}/cgi-bin/review.cgi?id={lemma_id}"


def _to_int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def highlight_html(text: str, *, start, end, cls: str) -> str:
    start_i = _to_int(start)
    end_i = _to_int(end)
    if start_i is None or end_i is None:
        return escape(text or "")
    if start_i < 0 or end_i <= start_i or end_i > len(text):
        return escape(text or "")
    return (
        escape(text[:start_i])
        + f'<span class="hl {cls}">'
        + escape(text[start_i:end_i])
        + "</span>"
        + escape(text[end_i:])
    )


def highlight_snippet_html(
    text: str, *, start, end, cls: str, context: int = 140
) -> str:
    start_i = _to_int(start)
    end_i = _to_int(end)
    if start_i is None or end_i is None:
        return escape(text or "")
    if start_i < 0 or end_i <= start_i or end_i > len(text):
        return escape(text or "")
    left = max(0, start_i - int(context))
    right = min(len(text), end_i + int(context))
    prefix = "…" if left > 0 else ""
    suffix = "…" if right < len(text) else ""
    return (
        escape(prefix)
        + escape(text[left:start_i])
        + f'<span class="hl {cls}">'
        + escape(text[start_i:end_i])
        + "</span>"
        + escape(text[end_i:right])
        + escape(suffix)
    )


def highlight_many_html(text: str, spans: list[dict]) -> str:
    if not spans:
        return escape(text or "")

    cleaned: list[tuple[int, int, str, float]] = []
    for sp in spans:
        start_i = _to_int(sp.get("start"))
        end_i = _to_int(sp.get("end"))
        cls = (sp.get("cls") or "").strip()
        priority = sp.get("priority", 0.0)
        try:
            priority_f = float(priority)
        except Exception:
            priority_f = 0.0
        if start_i is None or end_i is None:
            continue
        if start_i < 0 or end_i <= start_i or end_i > len(text):
            continue
        if not cls:
            continue
        cleaned.append((start_i, end_i, cls, priority_f))

    if not cleaned:
        return escape(text or "")

    breakpoints = {0, len(text)}
    for start_i, end_i, _cls, _prio in cleaned:
        breakpoints.add(start_i)
        breakpoints.add(end_i)

    points = sorted(breakpoints)
    intervals: list[tuple[int, int, str | None]] = []
    for i in range(len(points) - 1):
        a, b = points[i], points[i + 1]
        if a >= b:
            continue
        covering = [
            (s, e, cls, prio)
            for (s, e, cls, prio) in cleaned
            if s <= a and e >= b
        ]
        if not covering:
            intervals.append((a, b, None))
            continue
        best = max(covering, key=lambda t: (t[3], t[1] - t[0]))
        intervals.append((a, b, best[2]))

    merged: list[tuple[int, int, str | None]] = []
    for a, b, cls in intervals:
        if merged and merged[-1][2] == cls and merged[-1][1] == a:
            merged[-1] = (merged[-1][0], b, cls)
        else:
            merged.append((a, b, cls))

    parts: list[str] = []
    for a, b, cls in merged:
        seg = escape(text[a:b])
        if cls:
            parts.append(f'<span class="hl {cls}">{seg}</span>')
        else:
            parts.append(seg)
    return "".join(parts)


def gadget_srcdoc(*, html: str | None, css: str | None, js: str | None) -> str:
    body_html = html or ""
    style_css = (css or "").replace("</style>", "<\\/style>")
    script_js = (js or "").replace("</script>", "<\\/script>")
    return (
        "<!doctype html>"
        "<html lang=\"en\">"
        "<head>"
        "<meta charset=\"utf-8\"/>"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"/>"
        "<style>"
        + style_css
        + "</style>"
        "</head>"
        "<body>"
        + body_html
        + "<script>"
        + script_js
        + "</script>"
        "</body>"
        "</html>"
    )


def render_shell(*, title: str, body_html: str) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>{escape(title)}</title>
  <link rel="stylesheet" href="/style.css" />
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

    stephanos_base_url = _stephanos_base_url("https://stephanos.symmachus.org")

    rows_html = []
    for row in lines:
        line_id = row["id"]
        ref = row["ref"]
        slug = ref_to_slug(ref)
        summary = row.get("summary") or ""
        ref_major = row.get("ref_major")
        ref_minor = row.get("ref_minor")

        status_html = []
        status_html.append(
            '<span class="tag ok">translated</span>'
            if row.get("english_translation")
            else '<span class="tag todo">needs translation</span>'
        )
        status_html.append(
            '<span class="tag ok">summarized</span>'
            if row.get("summary")
            else '<span class="tag todo">needs summary</span>'
        )
        status_cell = " ".join(status_html)

        overlap = top_overlap_by_line.get(line_id)
        overlap_cell = "—"
        char_cell = "—"
        word_cell = "—"
        char_val = ""
        word_val = ""
        if overlap:
            lemma_id = int(overlap["stephanos_lemma_id"])
            meineke_id = overlap.get("stephanos_meineke_id") or f"lemma {lemma_id}"
            headword = overlap.get("stephanos_headword") or ""
            url = stephanos_entry_url(
                base_url=stephanos_base_url, lemma_id=lemma_id, headword=headword
            )
            label = (f"{meineke_id} {headword}").strip()
            overlap_cell = f'<a href="{escape(url)}" target="_blank" rel="noopener">{escape(label)}</a>'
            char_cell = f"{overlap['char_lcs_ratio']*100:.1f}%"
            word_cell = f"{overlap['word_lcs_ratio']*100:.1f}%"
            char_val = f"{overlap['char_lcs_ratio']*100:.6f}"
            word_val = f"{overlap['word_lcs_ratio']*100:.6f}"

        hay = f"{ref} {summary}"
        if overlap:
            hay += f" {overlap.get('stephanos_meineke_id') or ''} {overlap.get('stephanos_headword') or ''}"

        rows_html.append(
            f"""
            <tr data-hay="{escape(hay)}" data-ref-major="{escape(str(ref_major) if ref_major is not None else '')}" data-ref-minor="{escape(str(ref_minor) if ref_minor is not None else '')}" data-char="{escape(char_val)}" data-word="{escape(word_val)}">
              <td class="ref"><a href="passages/{escape(slug)}.html">{escape(ref)}</a></td>
              <td>{escape(summary) if summary else '<span class="pending">—</span>'}</td>
              <td class="small">{status_cell}</td>
              <td>{overlap_cell}</td>
              <td class="small">{escape(char_cell)}</td>
              <td class="small">{escape(word_cell)}</td>
            </tr>
            """.strip()
        )

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
      <input id="q" type="search" placeholder="Filter by ref, summary, or overlap…" autocomplete="off" />
      <a class="btn" href="index.html">Index</a>
      <a class="btn" href="analysis/index.html">Analysis</a>
    </div>
    <div class="table-wrap">
      <table class="tbl" id="tbl">
        <thead>
          <tr>
            <th class="sortable" data-sort="ref">Ref<span class="arrow"></span></th>
            <th>Summary</th>
            <th>Status</th>
            <th>Top overlap (Stephanos)</th>
            <th class="sortable" data-sort="char">Char<span class="arrow"></span></th>
            <th class="sortable" data-sort="word">Word<span class="arrow"></span></th>
          </tr>
        </thead>
        <tbody>
          {"".join(rows_html)}
        </tbody>
      </table>
    </div>
    <div class="meta">Stats: <code id="stats">{stats_json}</code></div>
    <script>
      const q = document.getElementById('q');
      const rows = Array.from(document.querySelectorAll('#tbl tbody tr'));
      const tbody = document.querySelector('#tbl tbody');
      const headers = Array.from(document.querySelectorAll('#tbl thead th[data-sort]'));
      let sortKey = 'ref';
      let sortDir = 1; // 1=asc, -1=desc

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

      function refParts(row){{
        const maj = parseInt(row.dataset.refMajor || '', 10);
        const min = parseInt(row.dataset.refMinor || '', 10);
        if (Number.isFinite(maj) && Number.isFinite(min)) return [maj, min];
        const refText = (row.querySelector('td.ref')?.innerText || '').trim();
        const m = refText.match(/^(\\d+)\\.(\\d+)$/);
        if (m) return [parseInt(m[1], 10), parseInt(m[2], 10)];
        return [1e9, 1e9];
      }}

      function metricVal(row, key){{
        const v = parseFloat(row.dataset[key] || '');
        return Number.isFinite(v) ? v : null;
      }}

      function compareRows(a, b){{
        if (sortKey === 'ref') {{
          const [am, an] = refParts(a);
          const [bm, bn] = refParts(b);
          if (am !== bm) return (am - bm) * sortDir;
          if (an !== bn) return (an - bn) * sortDir;
          return a.innerText.localeCompare(b.innerText) * sortDir;
        }}
        if (sortKey === 'char' || sortKey === 'word') {{
          const av = metricVal(a, sortKey);
          const bv = metricVal(b, sortKey);
          if (av === null && bv === null) {{
            const [am, an] = refParts(a);
            const [bm, bn] = refParts(b);
            if (am !== bm) return am - bm;
            if (an !== bn) return an - bn;
            return 0;
          }}
          if (av === null) return 1; // missing always last
          if (bv === null) return -1;
          if (av !== bv) return (av - bv) * sortDir;
          const [am, an] = refParts(a);
          const [bm, bn] = refParts(b);
          if (am !== bm) return am - bm;
          if (an !== bn) return an - bn;
          return 0;
        }}
        return 0;
      }}

      function renderSortIndicators(){{
        for (const th of headers){{
          const arrow = th.querySelector('.arrow');
          if (!arrow) continue;
          if (th.dataset.sort === sortKey) {{
            arrow.textContent = sortDir === 1 ? '▲' : '▼';
          }} else {{
            arrow.textContent = '';
          }}
        }}
      }}

      function sortBy(key){{
        if (sortKey === key) {{
          sortDir *= -1;
        }} else {{
          sortKey = key;
          sortDir = (key === 'ref') ? 1 : -1; // metrics default desc
        }}
        rows.sort(compareRows);
        for (const el of rows) tbody.appendChild(el);
        renderSortIndicators();
      }}

      for (const th of headers){{
        th.addEventListener('click', () => sortBy(th.dataset.sort));
      }}
      renderSortIndicators();
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
    gadget_html: str | None,
    gadget_css: str | None,
    gadget_js: str | None,
    overlaps: list[dict],
    stephanos_text_by_lemma_id: dict[int, dict],
) -> str:
    title = f"{site_title} — {ref}"
    stephanos_base_url = _stephanos_base_url("https://stephanos.symmachus.org")

    highlight_palette = ["c0", "c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8", "c9"]
    for i, ov in enumerate(overlaps):
        ov["_color_cls"] = highlight_palette[i % len(highlight_palette)]

    greek_html = highlight_many_html(
        greek_text or "",
        [
            {
                "start": ov.get("herodian_char_start"),
                "end": ov.get("herodian_char_end"),
                "cls": ov.get("_color_cls"),
                "priority": ov.get("char_lcs_len") or 0,
            }
            for ov in overlaps
        ],
    )

    overlaps_html = []
    for ov in overlaps:
        lemma_id = int(ov["stephanos_lemma_id"])
        meineke_id = ov.get("stephanos_meineke_id") or ""
        headword = ov.get("stephanos_headword") or ""
        char_pct = f"{ov['char_lcs_ratio']*100:.1f}%"
        word_pct = f"{ov['word_lcs_ratio']*100:.1f}%"
        stephanos_text = stephanos_text_by_lemma_id.get(lemma_id, {}).get("text_body") or ""
        stephanos_url = stephanos_entry_url(
            base_url=stephanos_base_url, lemma_id=lemma_id, headword=headword
        )
        color_cls = (ov.get("_color_cls") or "").strip()

        label = (f"{meineke_id} {headword}").strip() or f"lemma {lemma_id}"
        swatch = f'<span class="swatch {escape(color_cls)}"></span>' if color_cls else ""
        herodian_snippet = highlight_snippet_html(
            greek_text or "",
            start=ov.get("herodian_char_start"),
            end=ov.get("herodian_char_end"),
            cls=color_cls or "hl-h",
            context=160,
        )
        stephanos_snippet = highlight_snippet_html(
            stephanos_text,
            start=ov.get("stephanos_char_start"),
            end=ov.get("stephanos_char_end"),
            cls=color_cls or "hl-s",
            context=220,
        )

        overlaps_html.append(
            f"""
            <div class="row">
              <div class="row-head">
                <div class="ref">{swatch}<a href="{escape(stephanos_url)}" target="_blank" rel="noopener">{escape(label)}</a></div>
                <div class="kvs">
                  <span class="kv">char LCS {escape(str(ov['char_lcs_len']))} ({escape(char_pct)})</span>
                  <span class="kv">word LCS {escape(str(ov['word_lcs_len']))} ({escape(word_pct)})</span>
                </div>
              </div>
              <details>
                <summary>Show overlap highlight</summary>
                <div class="grid">
                  <pre class="greek" lang="el">{herodian_snippet}</pre>
                  <pre class="greek" lang="el">{stephanos_snippet}</pre>
                </div>
              </details>
            </div>
            """.strip()
        )

    overlaps_block = (
        "<div class='meta'><span class='pending'>No overlaps computed yet.</span></div>"
        if not overlaps_html
        else "\n".join(overlaps_html)
    )

    gadget_block = "<span class='pending'>No gadget yet.</span>"
    if gadget_html is not None or gadget_css is not None or gadget_js is not None:
        srcdoc = gadget_srcdoc(html=gadget_html, css=gadget_css, js=gadget_js)
        gadget_block = (
            f'<iframe class="gadget-frame" sandbox="allow-scripts allow-forms" '
            f'loading="lazy" referrerpolicy="no-referrer" srcdoc="{escape(srcdoc)}"></iframe>'
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
	        <div class="greek" lang="el">{greek_html}</div>
	        <div class="english">{escape(english_translation) if english_translation else '<span class="pending">Pending translation</span>'}</div>
	      </div>
	    </div>
    <h2>Gadget</h2>
    <div class="row">
      <div class="summary">A small interactive toy based on this passage (experimental).</div>
      {gadget_block}
    </div>
    <h2>Overlaps (Stephanos, Meineke)</h2>
    {overlaps_block}
    """.strip()

    return render_shell(title=title, body_html=body)


def _greek_casefold_strip(text: str) -> str:
    s = (text or "").casefold()
    s = unicodedata.normalize("NFD", s)
    out = []
    for ch in s:
        if unicodedata.combining(ch):
            continue
        if ch == "ϲ":
            ch = "σ"
        if unicodedata.category(ch).startswith("L"):
            out.append(ch)
        else:
            out.append(" ")
    return " ".join("".join(out).split())


def _render_analysis_index(*, site_title: str, summary_html: str) -> str:
    body = f"""
    <header>
      <h1><a href="../index.html">{escape(site_title)}</a></h1>
      <div class="meta"><span class="pill">Analysis</span></div>
    </header>
    <div class="controls">
      <a class="btn" href="../index.html">← Index</a>
      <a class="btn" href="reuse_predictors_words.html">TF‑IDF + LogReg (words)</a>
      <a class="btn" href="reuse_predictors_ngrams_2_3.html">TF‑IDF + LogReg (2–3 grams)</a>
    </div>
    {summary_html}
    """.strip()
    return render_shell(title=f"{site_title} — Analysis", body_html=body)


def _render_predictors_page(
    *,
    site_title: str,
    title_suffix: str,
    subtitle: str,
    meta: list[str],
    positive: list[tuple[str, float]],
    negative: list[tuple[str, float]],
) -> str:
    meta_html = " ".join(f'<span class="pill">{escape(m)}</span>' for m in meta)

    def _table(rows: list[tuple[str, float]], heading: str) -> str:
        tr = []
        for i, (term, coef) in enumerate(rows, start=1):
            tr.append(
                f"<tr><td class='small'>{i}</td><td>{escape(term)}</td><td class='small'>{coef:+.4f}</td></tr>"
            )
        return f"""
        <div class="table-wrap">
          <table class="tbl">
            <thead><tr><th colspan="3">{escape(heading)}</th></tr><tr><th>#</th><th>Term</th><th>Coef</th></tr></thead>
            <tbody>{''.join(tr)}</tbody>
          </table>
        </div>
        """.strip()

    body = f"""
    <header>
      <h1><a href="../index.html">{escape(site_title)}</a></h1>
      <div class="meta">{meta_html}</div>
    </header>
    <div class="controls">
      <a class="btn" href="../index.html">← Index</a>
      <a class="btn" href="index.html">Analysis</a>
    </div>
    <div class="row">
      <div class="ref">{escape(title_suffix)}</div>
      <div class="summary">{escape(subtitle)}</div>
    </div>
    <div class="grid">
      {_table(positive, 'Top re‑use predictors')}
      {_table(negative, 'Top no‑re‑use predictors')}
    </div>
    """.strip()

    return render_shell(title=f"{site_title} — {title_suffix}", body_html=body)


def _generate_analysis_pages(
    *,
    out_dir: Path,
    site_title: str,
    lines: list[dict],
    overlaps_by_line: dict[int, list[dict]],
    latest_run_id: int | None,
    reuse_char_lcs_min: int,
    reuse_word_lcs_min: int,
    top_k: int = 50,
) -> None:
    analysis_dir = out_dir / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)

    if not latest_run_id:
        (analysis_dir / "index.html").write_text(
            _render_analysis_index(
                site_title=site_title,
                summary_html="<div class='row'><div class='summary'><span class='pending'>No overlap run found yet.</span></div></div>",
            ),
            encoding="utf-8",
        )
        return

    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import Pipeline
    except Exception:
        (analysis_dir / "index.html").write_text(
            _render_analysis_index(
                site_title=site_title,
                summary_html="<div class='row'><div class='summary'><span class='pending'>Install scikit-learn to generate TF‑IDF analysis.</span></div></div>",
            ),
            encoding="utf-8",
        )
        return

    docs: list[str] = []
    y: list[int] = []
    for row in lines:
        line_id = int(row["id"])
        greek = row.get("greek_text") or ""
        ovs = overlaps_by_line.get(line_id) or []
        reused = any(
            (ov.get("char_lcs_len") or 0) >= reuse_char_lcs_min
            and (ov.get("word_lcs_len") or 0) >= reuse_word_lcs_min
            for ov in ovs
        )
        docs.append(greek)
        y.append(1 if reused else 0)

    n_pos = sum(y)
    n_total = len(y)
    n_neg = n_total - n_pos

    threshold_desc = f"reuse=1 if char≥{reuse_char_lcs_min} AND word≥{reuse_word_lcs_min} (run {latest_run_id})"

    def run_model(*, ngram_range: tuple[int, int], filename: str, label: str) -> None:
        vectorizer = TfidfVectorizer(
            preprocessor=_greek_casefold_strip,
            token_pattern=r"(?u)\b[^\W\d_]{2,}\b",
            ngram_range=ngram_range,
            min_df=2,
        )
        clf = LogisticRegression(
            C=1.0,
            solver="liblinear",
            max_iter=2000,
        )
        pipe = Pipeline([("tfidf", vectorizer), ("logreg", clf)])
        pipe.fit(docs, y)

        feature_names = pipe.named_steps["tfidf"].get_feature_names_out()
        coefs = pipe.named_steps["logreg"].coef_[0]
        pairs = list(zip(feature_names, coefs))
        pairs.sort(key=lambda t: float(t[1]), reverse=True)
        positive = [(t, float(c)) for (t, c) in pairs[:top_k]]
        negative = [(t, float(c)) for (t, c) in pairs[-top_k:]][::-1]

        (analysis_dir / filename).write_text(
            _render_predictors_page(
                site_title=site_title,
                title_suffix=label,
                subtitle=threshold_desc,
                meta=[
                    f"{n_total} docs",
                    f"{n_pos} reuse",
                    f"{n_neg} no‑reuse",
                    f"ngram={ngram_range[0]}–{ngram_range[1]}",
                    "logreg L2 (C=1.0)",
                ],
                positive=positive,
                negative=negative,
            ),
            encoding="utf-8",
        )

    run_model(ngram_range=(1, 1), filename="reuse_predictors_words.html", label="TF‑IDF + LogReg (words)")
    run_model(
        ngram_range=(2, 3),
        filename="reuse_predictors_ngrams_2_3.html",
        label="TF‑IDF + LogReg (word 2–3 grams)",
    )

    (analysis_dir / "index.html").write_text(
        _render_analysis_index(
            site_title=site_title,
            summary_html=(
                "<div class='row'>"
                f"<div class='summary'>Dataset: <code>{escape(threshold_desc)}</code> — {n_pos} reuse / {n_neg} no‑reuse.</div>"
                "</div>"
            ),
        ),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate static site from cathpros_lines.")
    parser.add_argument("--out", default="site", help="Output directory (default: site)")
    parser.add_argument("--overlap-metric-version", default="v1", help="Overlap metric version to display (default: v1)")
    parser.add_argument("--reuse-char-lcs-min", type=int, default=80, help="Reuse label threshold: min char LCS length (default: 80)")
    parser.add_argument("--reuse-word-lcs-min", type=int, default=15, help="Reuse label threshold: min word LCS length (default: 15)")
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
                SELECT
                  id,
                  ref,
                  ref_major,
                  ref_minor,
                  greek_text,
                  english_translation,
                  summary,
                  gadget_html,
                  gadget_css,
                  gadget_js,
                  translated_at
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
                      herodian_char_start,
                      herodian_char_end,
                      stephanos_char_start,
                      stephanos_char_end,
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
                "ref_major": r.get("ref_major"),
                "ref_minor": r.get("ref_minor"),
                "greek_text": r["greek_text"],
                "english_translation": r["english_translation"],
                "summary": r.get("summary"),
                "gadget_html": r.get("gadget_html"),
                "gadget_css": r.get("gadget_css"),
                "gadget_js": r.get("gadget_js"),
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
                "herodian_char_start": ov.get("herodian_char_start"),
                "herodian_char_end": ov.get("herodian_char_end"),
                "stephanos_char_start": ov.get("stephanos_char_start"),
                "stephanos_char_end": ov.get("stephanos_char_end"),
                "word_lcs_len": int(ov["word_lcs_len"]),
                "word_lcs_ratio": float(ov["word_lcs_ratio"]),
            }
        )

    for ovs in overlaps_by_line.values():
        ovs.sort(
            key=lambda o: (
                int(o.get("char_lcs_len") or 0),
                int(o.get("word_lcs_len") or 0),
                float(o.get("char_lcs_ratio") or 0.0),
                float(o.get("word_lcs_ratio") or 0.0),
            ),
            reverse=True,
        )

    top_overlap_by_line: dict[int, dict] = {}
    for line_id, ovs in overlaps_by_line.items():
        if ovs:
            top_overlap_by_line[line_id] = ovs[0]

    # Fetch Stephanos texts for the overlap candidates we will show.
    stephanos_text_by_lemma_id: dict[int, dict] = {}
    lemma_ids = sorted({ov["stephanos_lemma_id"] for ovs in overlaps_by_line.values() for ov in ovs[:10]})
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

    _generate_analysis_pages(
        out_dir=out_dir,
        site_title=site_title,
        lines=lines,
        overlaps_by_line=overlaps_by_line,
        latest_run_id=latest_run_id,
        reuse_char_lcs_min=int(args.reuse_char_lcs_min),
        reuse_word_lcs_min=int(args.reuse_word_lcs_min),
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
                gadget_html=row.get("gadget_html"),
                gadget_css=row.get("gadget_css"),
                gadget_js=row.get("gadget_js"),
                overlaps=(overlaps_by_line.get(row["id"]) or [])[:10],
                stephanos_text_by_lemma_id=stephanos_text_by_lemma_id,
            ),
            encoding="utf-8",
        )

    print(f"OK: wrote {out_dir}/index.html and {len(lines)} passage pages.")


if __name__ == "__main__":
    main()
