"""Safe read-only web search and documentation lookup helpers."""

from __future__ import annotations

import ipaddress
import re
import socket
from html import unescape
from typing import Dict, List
from urllib.parse import urlparse

import httpx

_LINK_RE = re.compile(
    r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_SNIPPET_RE = re.compile(
    r'<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")


def _clean_html(raw: str) -> str:
    return unescape(_TAG_RE.sub("", raw)).strip()


def is_safe_public_url(url: str) -> bool:
    """Block SSRF against loopback, private LAN, or metadata IP addresses."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    host = parsed.hostname.lower()
    if host in ("localhost", "127.0.0.1", "::1"):
        return False
    try:
        ip = ipaddress.ip_address(socket.gethostbyname(host))
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return False
    except Exception:  # noqa: BLE001
        return False
    return True


async def search_web(
    query: str,
    limit: int = 5,
    client_factory=None,  # type: ignore[no-untyped-def]
) -> List[Dict[str, str]]:
    """Query DuckDuckGo HTML search and return structured title/url/snippet results."""
    clean_query = query.strip()
    if not clean_query:
        return []

    factory = client_factory or (lambda t: httpx.AsyncClient(timeout=t, follow_redirects=True))
    async with factory(10.0) as client:
        response = await client.post(
            "https://html.duckduckgo.com/html/",
            data={"q": clean_query},
            headers={"User-Agent": "Muquissi-Assistant/1.0"},
        )
        if response.status_code >= 400:
            raise RuntimeError(f"Pesquisa web devolveu HTTP {response.status_code}")
        html = response.text

    links = _LINK_RE.findall(html)
    snippets = _SNIPPET_RE.findall(html)
    results: List[Dict[str, str]] = []
    for idx, (href, title_html) in enumerate(links[:limit]):
        snippet = _clean_html(snippets[idx]) if idx < len(snippets) else ""
        results.append(
            {
                "title": _clean_html(title_html),
                "url": href,
                "snippet": snippet,
            }
        )
    return results
