"""Offline gadget constraints shared by local and cloud workflows."""
import re

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

