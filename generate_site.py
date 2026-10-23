#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import re
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path



def build_time():
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    return datetime.fromtimestamp(int(epoch), timezone.utc) if epoch else datetime.now(timezone.utc)


def _site_title(default: str) -> str:
    try:
        from config import SITE_TITLE as CONFIG_SITE_TITLE
    except ImportError:
        CONFIG_SITE_TITLE = None
    return (CONFIG_SITE_TITLE or default).strip()


def _site_contact_name(default: str) -> str:
    try:
        from config import SITE_CONTACT_NAME as CONFIG_SITE_CONTACT_NAME
    except ImportError:
        CONFIG_SITE_CONTACT_NAME = None
    return (CONFIG_SITE_CONTACT_NAME or default).strip()


def _site_contact_emails(default: list[str]) -> list[str]:
    try:
        from config import SITE_CONTACT_EMAILS as CONFIG_SITE_CONTACT_EMAILS
    except ImportError:
        CONFIG_SITE_CONTACT_EMAILS = None

    val = CONFIG_SITE_CONTACT_EMAILS
    if val in (None, ""):
        return default
    if isinstance(val, str):
        parts = re.split(r"[,\s;]+", val.strip())
        emails = [p.strip() for p in parts if p.strip()]
    elif isinstance(val, (list, tuple)):
        emails = [str(x).strip() for x in val if str(x).strip()]
    else:
        return default

    emails = [e for e in emails if "@" in e]
    return emails or default


def _config_int(attr: str, default: int) -> int:
    try:
        import config as _config
    except ImportError:
        _config = None
    raw = getattr(_config, attr, None) if _config else None
    if raw in (None, ""):
        return int(default)
    try:
        return int(raw)
    except Exception:
        return int(default)


def _config_str(attr: str, default: str) -> str:
    try:
        import config as _config
    except ImportError:
        _config = None
    raw = getattr(_config, attr, None) if _config else None
    if raw in (None, ""):
        return str(default)
    return str(raw)


def _env_or_config_int(env_name: str, config_attr: str, default: int) -> int:
    raw_env = os.getenv(env_name)
    if raw_env not in (None, ""):
        try:
            return int(raw_env)
        except Exception:
            pass
    return _config_int(config_attr, default)


def _to_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _fmt_utc(dt: datetime | None) -> str:
    dt_utc = _to_utc(dt)
    if dt_utc is None:
        return "—"
    return dt_utc.strftime("%Y-%m-%d %H:%M UTC")


def _estimate_backlog(
    *, remaining: int, per_run_capacity: int, runs_per_day: int, now_utc: datetime
) -> dict[str, int | datetime | None]:
    remaining_i = max(0, int(remaining or 0))
    per_run_i = max(0, int(per_run_capacity or 0))
    runs_per_day_i = max(1, int(runs_per_day or 1))
    if remaining_i <= 0:
        return {
            "remaining": 0,
            "runs_left": 0,
            "days_left": 0,
            "eta": now_utc,
        }
    if per_run_i <= 0:
        return {
            "remaining": remaining_i,
            "runs_left": None,
            "days_left": None,
            "eta": None,
        }
    runs_left = int(math.ceil(remaining_i / per_run_i))
    days_left = int(math.ceil(runs_left / runs_per_day_i))
    eta = now_utc + timedelta(days=days_left)
    return {
        "remaining": remaining_i,
        "runs_left": runs_left,
        "days_left": days_left,
        "eta": eta,
    }


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
.banner{
  margin:0 0 16px;
  padding:12px 14px;
  border-radius:14px;
  border:1px solid var(--border);
  background:rgba(17,26,51,.55);
}
.banner.warn{
  border-color:#5a3b24;
  background:rgba(90,59,36,.20);
}
.banner .badge{
  display:inline-block;
  padding:2px 10px;
  border-radius:999px;
  border:1px solid #5a3b24;
  background:rgba(90,59,36,.35);
  color:#ffd9c2;
  font-size:12px;
  letter-spacing:.04em;
  text-transform:uppercase;
  margin-right:8px;
  vertical-align:1px;
}
.banner .muted{color:var(--muted);}
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
.btn.tiny{padding:6px 10px;font-size:12px;}
button.btn{cursor:pointer;font:inherit;}
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
.prose{
  font-size:15px;
  line-height:1.55;
}
.prose p{margin:0 0 10px;}
.prose ul{margin:0 0 10px 20px;}
.prose li{margin:0 0 6px;}
.pending{color:var(--muted);font-style:italic;}
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














def gadget_srcdoc(*, html: str | None, css: str | None, js: str | None) -> str:
    from gadget_validation import GADGET_CSP
    body_html = html or ""
    style_css = (css or "").replace("</style>", "<\\/style>")
    script_js = (js or "").replace("</script>", "<\\/script>")
    return (
        "<!doctype html>"
        "<html lang=\"en\">"
        "<head>"
        "<meta charset=\"utf-8\"/>"
        + '<meta http-equiv="Content-Security-Policy" content="' + GADGET_CSP + '"/>'
        +
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
    generated_at = build_time().strftime("%Y-%m-%d %H:%M UTC")
    contact_name = _site_contact_name("")
    contact_emails = _site_contact_emails(
        ["gregb@ifost.org.au", "greg.baker@mq.edu.au", "greg.baker@anu.edu.au"]
    )
    contact_email_codes = [[ord(ch) for ch in e] for e in contact_emails]
    contact_name_codes = [ord(ch) for ch in contact_name] if contact_name else []
    banner_html = """
    <div class="banner warn">
      <span class="badge">Warning</span>
      This is a translation of A. Lentz’s reconstructed 19th‑century Teubner text of Herodian’s <em>De Prosodia Catholica</em> (not a continuous ancient original).
      <a href="/about/lentz.html">About the Lentz edition</a><span class="muted">.</span>
    </div>
    """.strip()
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
    {banner_html}
    {body_html}
    <footer>
      <span id="contact-widget">
        <button class="btn tiny" id="contact-reveal" type="button">Contact</button>
        <span id="contact-details"></span>
        <noscript><span class="pending">Enable JavaScript to view.</span></noscript>
      </span>
      <span class="meta"> · Generated: {escape(generated_at)}</span>
      <script>
        (() => {{
          const btn = document.getElementById('contact-reveal');
          const out = document.getElementById('contact-details');
          if (!btn || !out) return;
          const name = {json.dumps(contact_name_codes)};
          const emails = {json.dumps(contact_email_codes)};
          const decode = (arr) => arr.map((c) => String.fromCharCode(c)).join('');
          let shown = false;
          function render() {{
            out.textContent = '';
            const parts = [];
            if (name && name.length) parts.push(decode(name));
            const emailLinks = [];
            for (const e of emails) {{
              const addr = decode(e);
              const a = document.createElement('a');
              a.href = 'mailto:' + addr;
              a.textContent = addr;
              a.rel = 'nofollow';
              emailLinks.push(a);
            }}
            if (emailLinks.length) {{
              if (parts.length) parts.push(' — ');
              for (let i = 0; i < emailLinks.length; i++) {{
                if (i) parts.push(' / ');
                parts.push(emailLinks[i]);
              }}
            }}
            for (const p of parts) {{
              if (typeof p === 'string') out.appendChild(document.createTextNode(p));
              else out.appendChild(p);
            }}
          }}
          btn.addEventListener('click', () => {{
            shown = !shown;
            btn.textContent = shown ? 'Hide' : 'Contact';
            if (shown) render();
            else out.textContent = '';
          }});
        }})();
      </script>
    </footer>
  </div>
</body>
</html>
"""


def render_index(*, title: str, stats: dict, lines: list[dict]) -> str:
    translated = stats["translated"]
    summarized = stats["summarized"]
    total = stats["total"]
    percent = (translated / total * 100.0) if total else 0.0
    percent_str = f"{percent:.1f}%"


    rows_html = []
    for row in lines:
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

        hay = f"{ref} {summary}"

        rows_html.append(
            f"""
            <tr data-hay="{escape(hay)}" data-ref-major="{escape(str(ref_major) if ref_major is not None else '')}" data-ref-minor="{escape(str(ref_minor) if ref_minor is not None else '')}">
              <td class="ref"><a href="passages/{escape(slug)}.html">{escape(ref)}</a></td>
              <td>{escape(summary) if summary else '<span class="pending">—</span>'}</td>
              <td class="small">{status_cell}</td>
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
      <input id="q" type="search" placeholder="Filter by ref or summary…" autocomplete="off" />
      <a class="btn" href="index.html">Index</a>
      <a class="btn" href="analysis/progress.html">Progress</a>
      <a class="btn" href="passages.json">Data (JSON)</a>
      <a class="btn" href="https://github.com/solresol/prosodia-catholica" target="_blank" rel="noopener">GitHub</a>
    </div>
    <div class="table-wrap">
      <table class="tbl" id="tbl">
        <thead>
          <tr>
            <th class="sortable" data-sort="ref">Ref<span class="arrow"></span></th>
            <th>Summary</th>
            <th>Status</th>
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

      function compareRows(a, b){{
        const [am, an] = refParts(a);
        const [bm, bn] = refParts(b);
        if (am !== bm) return (am - bm) * sortDir;
        if (an !== bn) return (an - bn) * sortDir;
        return a.innerText.localeCompare(b.innerText) * sortDir;
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
          sortDir = 1;
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
) -> str:
    title = f"{site_title} — {ref}"

    greek_html = escape(greek_text or "")

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
    """.strip()

    return render_shell(title=title, body_html=body)


def render_about_lentz(*, site_title: str) -> str:
    title = f"{site_title} — About the Lentz edition"
    body = f"""
    <header>
      <h1><a href="/index.html">{escape(site_title)}</a></h1>
      <div class="meta"><span class="pill">About the text</span></div>
    </header>
    <div class="controls">
      <a class="btn" href="/index.html">← Index</a>
      <a class="btn" href="/analysis/progress.html">Progress</a>
    </div>

    <div class="row">
      <div class="ref">What this site is</div>
      <div class="prose">
        <p>This project translates the Greek text of Herodian’s <em>Περὶ καθολικῆς προσῳδίας</em> (<em>De Prosodia Catholica</em>) as printed in the 19th‑century Teubner edition edited by <strong>A. Lentz</strong> (1867–1870), the version widely reused in modern digital corpora (including TLG).</p>
        <p>Herodian’s original <em>Περὶ καθολικῆς προσῳδίας</em> is not preserved as a complete work. What survives is fragmentary and mediated through later grammatical sources (quotations, excerpts, and epitomes).</p>
      </div>
    </div>

    <div class="row">
      <div class="ref">What it is not</div>
      <div class="prose">
        <p>It is <strong>not</strong> a clean, continuous transcript of an ancient manuscript of Herodian.</p>
        <p>Lentz’s Teubner text is a <strong>reconstruction</strong>: it attempts to re‑create a coherent “Herodian” by selecting, slicing, and re‑arranging material from multiple witnesses, and by inserting parallel material (including from the Stephanus of Byzantium tradition) according to Lentz’s hypothesis about the work’s original structure.</p>
      </div>
    </div>

    <div class="row">
      <div class="ref">Further reading</div>
      <div class="prose">
        <ul>
          <li>BMCR review noting the “idiosyncratic and arbitrary” character of Lentz’s reconstruction and its long influence: <a href="https://bmcr.brynmawr.edu/2019/2019.05.26/" target="_blank" rel="noopener">BMCR 2019.05.26</a></li>
          <li>Oxford (DPhil) thesis summary describing Lentz’s approach as reconstructive rather than a presentation of surviving evidence: <a href="https://ora.ox.ac.uk/objects/uuid:14988220-7ce2-48b0-b61e-3dc8c64eb732" target="_blank" rel="noopener">ORA record</a></li>
          <li>Bibliographic record for the Teubner volume: <a href="https://scaife.perseus.org/library/urn:cts:greekLit:tlg0087.tlg031.opp-grc1/" target="_blank" rel="noopener">Scaife / Perseus catalog entry</a></li>
        </ul>
        <p class="meta">If you quote or analyze passages from this site, cite Lentz’s edition explicitly and (when possible) track the passage back to the underlying source (epitome/fragment/Stephanus) rather than treating it as a single ancient witness.</p>
      </div>
    </div>
    """.strip()
    return render_shell(title=title, body_html=body)




def _render_progress_page(*, site_title: str, progress_data: dict) -> str:
    now_utc = _to_utc(progress_data.get("now_utc")) or build_time()
    runs_per_day = max(1, int(progress_data.get("runs_per_day") or 1))

    total_all = max(0, int(progress_data.get("total_all") or 0))
    total_non_e = max(0, int(progress_data.get("total_non_e") or 0))
    total_translatable = max(0, int(progress_data.get("total_translatable") or 0))
    translated_done = max(0, int(progress_data.get("translated_done") or 0))
    summarized_done = max(0, int(progress_data.get("summarized_done") or 0))
    gadget_done = max(0, int(progress_data.get("gadget_done") or 0))
    gadget_ready_pending = max(0, int(progress_data.get("gadget_ready_pending") or 0))
    gadget_blocked_translation = max(0, int(progress_data.get("gadget_blocked_translation") or 0))

    translation_limit = max(0, int(progress_data.get("translation_limit") or 0))
    summary_limit = max(0, int(progress_data.get("summary_limit") or 0))
    gadget_limit = max(0, int(progress_data.get("gadget_limit") or 0))

    source_tsv_rows_raw = progress_data.get("source_tsv_rows")
    source_tsv_rows = (
        max(0, int(source_tsv_rows_raw)) if source_tsv_rows_raw is not None else None
    )

    def _fmt_int(n: int | None) -> str:
        if n is None:
            return "—"
        return f"{int(n):,}"

    def _fmt_estimate(
        est: dict[str, int | datetime | None] | None,
    ) -> tuple[str, str, str]:
        if not est:
            return "—", "—", "unknown"
        remaining = int(est.get("remaining") or 0)
        days_left = est.get("days_left")
        eta = est.get("eta")
        runs_left = est.get("runs_left")
        if remaining <= 0:
            return "0", "0", "complete"
        runs_text = "—" if runs_left is None else str(int(runs_left))
        days_text = "—" if days_left is None else str(int(days_left))
        if eta is None:
            return runs_text, days_text, "blocked (limit=0)"
        return runs_text, days_text, _fmt_utc(_to_utc(eta))

    backlog_rows: list[str] = []
    backlog_estimates: list[dict[str, int | datetime | None]] = []
    blocked_tasks: list[str] = []

    if source_tsv_rows is not None:
        import_done = min(total_all, source_tsv_rows)
        import_remaining = max(0, source_tsv_rows - import_done)
        import_est = _estimate_backlog(
            remaining=import_remaining,
            per_run_capacity=max(source_tsv_rows, 1),
            runs_per_day=runs_per_day,
            now_utc=now_utc,
        )
        if import_remaining > 0 and import_est.get("eta") is None:
            blocked_tasks.append("import")
        if import_remaining > 0:
            backlog_estimates.append(import_est)
        import_runs, import_days, import_eta = _fmt_estimate(import_est)
        backlog_rows.append(
            f"<tr><td class='small'>2</td><td>import_herodian_tsv.py</td>"
            f"<td class='small'>{_fmt_int(import_done)}/{_fmt_int(source_tsv_rows)}</td>"
            f"<td class='small'>{_fmt_int(import_remaining)}</td>"
            f"<td class='small'>full file</td>"
            f"<td class='small'>{escape(import_runs)}</td>"
            f"<td class='small'>{escape(import_days)}</td>"
            f"<td class='small'>{escape(import_eta)}</td>"
            f"<td class='small'>{escape(_fmt_utc(progress_data.get('latest_imported_at')))}</td>"
            f"<td>TSV source rows known.</td></tr>"
        )
    else:
        backlog_rows.append(
            f"<tr><td class='small'>2</td><td>import_herodian_tsv.py</td>"
            f"<td class='small'>{_fmt_int(total_all)}/?</td>"
            f"<td class='small'>—</td>"
            f"<td class='small'>full file</td>"
            f"<td class='small'>—</td>"
            f"<td class='small'>—</td>"
            f"<td class='small'>unknown (TSV missing)</td>"
            f"<td class='small'>{escape(_fmt_utc(progress_data.get('latest_imported_at')))}</td>"
            f"<td>TSV source file not found on this host.</td></tr>"
        )

    translation_remaining = max(0, total_translatable - translated_done)
    translation_est = _estimate_backlog(
        remaining=translation_remaining,
        per_run_capacity=translation_limit,
        runs_per_day=runs_per_day,
        now_utc=now_utc,
    )
    if translation_remaining > 0:
        backlog_estimates.append(translation_est)
    if translation_remaining > 0 and translation_est.get("eta") is None:
        blocked_tasks.append("translation")
    trans_runs, trans_days, trans_eta = _fmt_estimate(translation_est)
    backlog_rows.append(
        f"<tr><td class='small'>3</td><td>translate_lines.py</td>"
        f"<td class='small'>{_fmt_int(translated_done)}/{_fmt_int(total_translatable)}</td>"
        f"<td class='small'>{_fmt_int(translation_remaining)}</td>"
        f"<td class='small'>{_fmt_int(translation_limit)}/run</td>"
        f"<td class='small'>{escape(trans_runs)}</td>"
        f"<td class='small'>{escape(trans_days)}</td>"
        f"<td class='small'>{escape(trans_eta)}</td>"
        f"<td class='small'>{escape(_fmt_utc(progress_data.get('latest_translated_at')))}</td>"
        f"<td>Scope excludes ref E and major 0.</td></tr>"
    )

    summary_remaining = max(0, total_non_e - summarized_done)
    summary_est = _estimate_backlog(
        remaining=summary_remaining,
        per_run_capacity=summary_limit,
        runs_per_day=runs_per_day,
        now_utc=now_utc,
    )
    if summary_remaining > 0:
        backlog_estimates.append(summary_est)
    if summary_remaining > 0 and summary_est.get("eta") is None:
        blocked_tasks.append("summary")
    sum_runs, sum_days, sum_eta = _fmt_estimate(summary_est)
    backlog_rows.append(
        f"<tr><td class='small'>3b</td><td>summarize_lines.py</td>"
        f"<td class='small'>{_fmt_int(summarized_done)}/{_fmt_int(total_non_e)}</td>"
        f"<td class='small'>{_fmt_int(summary_remaining)}</td>"
        f"<td class='small'>{_fmt_int(summary_limit)}/run</td>"
        f"<td class='small'>{escape(sum_runs)}</td>"
        f"<td class='small'>{escape(sum_days)}</td>"
        f"<td class='small'>{escape(sum_eta)}</td>"
        f"<td class='small'>{escape(_fmt_utc(progress_data.get('latest_summarized_at')))}</td>"
        f"<td>Scope excludes ref E.</td></tr>"
    )

    gadget_remaining = max(0, total_translatable - gadget_done)
    gadget_est = _estimate_backlog(
        remaining=gadget_remaining,
        per_run_capacity=gadget_limit,
        runs_per_day=runs_per_day,
        now_utc=now_utc,
    )
    if gadget_remaining > 0:
        backlog_estimates.append(gadget_est)
    if gadget_remaining > 0 and gadget_est.get("eta") is None:
        blocked_tasks.append("gadget")
    gad_runs, gad_days, gad_eta = _fmt_estimate(gadget_est)
    backlog_rows.append(
        f"<tr><td class='small'>3bb</td><td>gadgetize_lines.py</td>"
        f"<td class='small'>{_fmt_int(gadget_done)}/{_fmt_int(total_translatable)}</td>"
        f"<td class='small'>{_fmt_int(gadget_remaining)}</td>"
        f"<td class='small'>{_fmt_int(gadget_limit)}/run</td>"
        f"<td class='small'>{escape(gad_runs)}</td>"
        f"<td class='small'>{escape(gad_days)}</td>"
        f"<td class='small'>{escape(gad_eta)}</td>"
        f"<td class='small'>{escape(_fmt_utc(progress_data.get('latest_gadget_generated_at')))}</td>"
        f"<td>{_fmt_int(gadget_ready_pending)} ready; {_fmt_int(gadget_blocked_translation)} blocked on translation.</td></tr>"
    )

    if blocked_tasks:
        overall_eta_html = (
            "<span class='pending'>Blocked: set non-zero limits for "
            + escape(", ".join(blocked_tasks))
            + ".</span>"
        )
    else:
        days_candidates = [
            int(est.get("days_left") or 0)
            for est in backlog_estimates
            if est.get("days_left") is not None
        ]
        max_days = max(days_candidates) if days_candidates else 0
        if max_days <= 0:
            overall_eta_html = "All backlog tasks complete."
        else:
            overall_eta_html = (
                f"Estimated completion in {max_days} day(s): "
                f"<code>{escape(_fmt_utc(now_utc + timedelta(days=max_days)))}</code>."
            )

    recurring_rows = [
        "<tr><td class='small'>0</td><td>git pull (if clean)</td><td class='small'>daily</td>"
        "<td class='small'>no backlog</td><td class='small'>next cron run</td>"
        "<td>Runs only when working tree is clean.</td></tr>",
        "<tr><td class='small'>1</td><td>init_db.py</td><td class='small'>daily</td>"
        "<td class='small'>no backlog</td><td class='small'>same run</td>"
        "<td>Idempotent core schema check.</td></tr>",
        "<tr><td class='small'>4</td><td>generate_site.py</td><td class='small'>daily</td>"
        "<td class='small'>no backlog</td><td class='small'>same run</td>"
        f"<td>This page generated at {_fmt_utc(now_utc)}.</td></tr>",
        "<tr><td class='small'>5</td><td>rsync deploy</td><td class='small'>daily</td>"
        "<td class='small'>no backlog</td><td class='small'>immediately after step 4</td>"
        "<td>Deploy target: configured in config.py (DEPLOY_HOST/DEPLOY_PATH).</td></tr>",
    ]

    cadence_text = "once per day" if runs_per_day == 1 else f"{runs_per_day} times per day"

    body = f"""
    <header>
      <h1><a href="../index.html">{escape(site_title)}</a></h1>
      <div class="meta"><span class="pill">Progress</span> <span class="pill">cron cadence: {escape(cadence_text)}</span></div>
    </header>
    <div class="controls">
      <a class="btn" href="../index.html">← Index</a>
    </div>
    <div class="row">
      <div class="summary">{overall_eta_html}</div>
    </div>
    <h2>Backlog Tasks (ETA)</h2>
    <div class="table-wrap">
      <table class="tbl">
        <thead>
          <tr>
            <th>Step</th><th>Task</th><th>Done/Total</th><th>Remaining</th><th>Capacity</th><th>Runs left</th><th>Days left</th><th>ETA (UTC)</th><th>Last success</th><th>Notes</th>
          </tr>
        </thead>
        <tbody>{"".join(backlog_rows)}</tbody>
      </table>
    </div>
    <h2>Recurring Daily Tasks</h2>
    <div class="table-wrap">
      <table class="tbl">
        <thead>
          <tr><th>Step</th><th>Task</th><th>Schedule</th><th>Backlog</th><th>ETA</th><th>Notes</th></tr>
        </thead>
        <tbody>{"".join(recurring_rows)}</tbody>
      </table>
    </div>
    <div class="row">
      <div class="summary">Estimates assume fixed per-run limits and regular cron execution ({escape(cadence_text)}).</div>
    </div>
    """.strip()

    return render_shell(title=f"{site_title} — Progress", body_html=body)














def main() -> None:
    parser = argparse.ArgumentParser(description="Generate static site from cathpros_lines.")
    parser.add_argument("--out", default="site", help="Output directory (default: site)")
    parser.add_argument("--content", type=Path, default=Path(__file__).parent / "content/passages.json")
    parser.add_argument("--database", action="store_true", help="Explicit rollback renderer; requires legacy DB configuration")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    passages_dir = out_dir / "passages"
    passages_dir.mkdir(parents=True, exist_ok=True)

    if args.database:
        from db import get_connection
        conn = get_connection(dict_cursor=True)
        progress_row = None
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
                    SELECT
                      COUNT(*) AS total_all,
                      COUNT(*) FILTER (WHERE ref NOT IN ('E')) AS total_non_e,
                      COUNT(*) FILTER (WHERE ref NOT IN ('E') AND COALESCE(ref_major, 1) <> 0) AS total_translatable,
                      COUNT(*) FILTER (WHERE ref NOT IN ('E') AND COALESCE(ref_major, 1) <> 0 AND english_translation IS NOT NULL) AS translated_done,
                      COUNT(*) FILTER (WHERE ref NOT IN ('E') AND summary IS NOT NULL) AS summarized_done,
                      COUNT(*) FILTER (WHERE ref NOT IN ('E') AND COALESCE(ref_major, 1) <> 0 AND gadget_html IS NOT NULL) AS gadget_done,
                      COUNT(*) FILTER (WHERE ref NOT IN ('E') AND COALESCE(ref_major, 1) <> 0 AND english_translation IS NOT NULL AND gadget_html IS NULL) AS gadget_ready_pending,
                      COUNT(*) FILTER (WHERE ref NOT IN ('E') AND COALESCE(ref_major, 1) <> 0 AND english_translation IS NULL) AS gadget_blocked_translation,
                      MAX(imported_at) AS latest_imported_at,
                      MAX(translated_at) AS latest_translated_at,
                      MAX(summarized_at) AS latest_summarized_at,
                      MAX(gadget_generated_at) AS latest_gadget_generated_at
                    FROM cathpros_lines
                    """
                )
                progress_row = cur.fetchone()

        finally:
            conn.close()
    else:
        from content_store import load, rendering_inputs
        rows, stats_row, progress_row = rendering_inputs(load(args.content))

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
    }

    source_tsv_path = Path("HerodianCathPros.txt")
    source_tsv_rows = None
    if source_tsv_path.exists():
        with source_tsv_path.open("r", encoding="utf-8") as f:
            source_tsv_rows = sum(1 for _ in f)

    runs_per_day = max(
        1, _env_or_config_int("PIPELINE_RUNS_PER_DAY", "PIPELINE_RUNS_PER_DAY", 1)
    )
    translation_limit = max(
        0, _env_or_config_int("TRANSLATION_LIMIT", "TRANSLATION_LIMIT", 5)
    )
    summary_limit = max(0, _env_or_config_int("SUMMARY_LIMIT", "SUMMARY_LIMIT", 25))
    gadget_limit = max(0, _env_or_config_int("GADGET_LIMIT", "GADGET_LIMIT", 1))

    progress_data = {
        "now_utc": build_time(),
        "runs_per_day": runs_per_day,
        "translation_limit": translation_limit,
        "summary_limit": summary_limit,
        "gadget_limit": gadget_limit,
        "total_all": int((progress_row or {}).get("total_all") or 0),
        "total_non_e": int((progress_row or {}).get("total_non_e") or 0),
        "total_translatable": int((progress_row or {}).get("total_translatable") or 0),
        "translated_done": int((progress_row or {}).get("translated_done") or 0),
        "summarized_done": int((progress_row or {}).get("summarized_done") or 0),
        "gadget_done": int((progress_row or {}).get("gadget_done") or 0),
        "gadget_ready_pending": int(
            (progress_row or {}).get("gadget_ready_pending") or 0
        ),
        "gadget_blocked_translation": int(
            (progress_row or {}).get("gadget_blocked_translation") or 0
        ),
        "latest_imported_at": (progress_row or {}).get("latest_imported_at"),
        "latest_translated_at": (progress_row or {}).get("latest_translated_at"),
        "latest_summarized_at": (progress_row or {}).get("latest_summarized_at"),
        "latest_gadget_generated_at": (
            progress_row or {}
        ).get("latest_gadget_generated_at"),
        "source_tsv_rows": source_tsv_rows,
        "source_tsv_path": str(source_tsv_path),
    }

    (out_dir / "style.css").write_text(STYLE_CSS.strip() + "\n", encoding="utf-8")

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

    if not args.database:
        legacy = args.content.parent / "legacy-lines.json"
        (out_dir / "lines.json").write_bytes(legacy.read_bytes())

    site_title = _site_title("Prosodia Catholica (Herodian)")
    (out_dir / "index.html").write_text(
        render_index(title=site_title, stats=stats, lines=lines),
        encoding="utf-8",
    )

    about_dir = out_dir / "about"
    about_dir.mkdir(parents=True, exist_ok=True)
    (about_dir / "lentz.html").write_text(
        render_about_lentz(site_title=site_title),
        encoding="utf-8",
    )

    analysis_dir = out_dir / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    # Remove only generated pages belonging to the retired feature. Do not touch
    # database history, source archives, or unrelated output files.
    for filename in ("index.html", "coverage.html", "reuse_predictors_words.html", "reuse_predictors_ngrams_2_3.html"):
        (analysis_dir / filename).unlink(missing_ok=True)
    (analysis_dir / "progress.html").write_text(
        _render_progress_page(site_title=site_title, progress_data=progress_data), encoding="utf-8"
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
            ),
            encoding="utf-8",
        )

    print(f"OK: wrote {out_dir}/index.html and {len(lines)} passage pages.")


if __name__ == "__main__":
    main()
