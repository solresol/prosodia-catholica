"""Offline constraints, backed by runtime CSP and actual browser tests.

Static checks are deliberately conservative and are not a JavaScript security
proof. Browser tests must block requests and independently review the source.
"""
from html.parser import HTMLParser
import re

GADGET_CSP = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
              "connect-src 'none'; img-src data:; font-src 'none'; media-src 'none'; "
              "frame-src 'none'; object-src 'none'; form-action 'none'; base-uri 'none'")
_FORBIDDEN_HTML_RE = re.compile(r'<\s*(script|style|link|iframe|object|embed|base|meta)\b', re.I)
_FORBIDDEN_JS_RE = re.compile(
    r'\b(fetch|XMLHttpRequest|WebSocket|EventSource|sendBeacon|location)\b|\bimport\s*\('
    r'|\b(?:window|globalThis|self|top|parent)\s*\.\s*open\s*\(', re.I)
_URL_RE = re.compile(r'https?://|(?<!:)//[^\s/]', re.I)


class _NavigationCheck(HTMLParser):
    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name.lower() in ('href', 'action', 'formaction', 'target', 'src', 'srcset', 'ping'):
                raise ValueError('Gadget navigation/resource attributes are not allowed')


def _validate_gadget(*, html: str, css: str, js: str) -> None:
    if _URL_RE.search(f'{html}\n{css}\n{js}'):
        raise ValueError('Gadget output contains a URL; must be offline/self-contained')
    if _FORBIDDEN_HTML_RE.search(html):
        raise ValueError('Gadget HTML contains forbidden embedded content')
    _NavigationCheck().feed(html)
    if _FORBIDDEN_JS_RE.search(js):
        raise ValueError('Gadget JS uses network, navigation or dynamic imports')
