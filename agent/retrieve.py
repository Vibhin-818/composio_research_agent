"""Retrieval layer: Composio Instant (Exa search + fetch) first, DuckDuckGo fallback."""

import re
from typing import Any
from urllib.parse import urlparse

import httpx
import trafilatura

try:
    from ddgs import DDGS
except ImportError:  # older installs keep the deprecated package name
    from duckduckgo_search import DDGS

from agent import cache, composio_tools

MAX_CHARS = 14000
MAX_PAGES = 5
PER_PAGE = 6000

NOISE = re.compile(
    r"(login|signin|sign-in|/logos?|/account|/checkout|cookie|privacy|terms)", re.I
)


def _host(hint: str) -> str:
    if not hint:
        return ""
    if not hint.startswith("http"):
        hint = "https://" + hint
    return urlparse(hint).netloc.replace("www.", "").lower()


def _is_noise(url: str) -> bool:
    if NOISE.search(url):
        return True
    parsed = urlparse(url)
    return parsed.path in ("", "/") and not parsed.query


def _score(url: str, root: str) -> int:
    u = url.lower()
    score = 0
    if root and root in u:
        score += 10
    if "developer" in u:
        score += 4
    if "docs" in u or "/api" in u or "api." in u:
        score += 3
    if "oauth" in u or "auth" in u:
        score += 2
    if "reference" in u or "rest" in u or "graphql" in u:
        score += 1
    return score


def _seeds(hint: str) -> list[str]:
    if not hint:
        return []
    base = hint if hint.startswith("http") else "https://" + hint
    root = _host(hint)
    bare = base.rstrip("/")
    return [
        f"https://developers.{root}",
        f"https://developer.{root}",
        f"https://docs.{root}",
        f"https://api.{root}",
        f"{bare}/docs",
        bare,
    ]


def _search(query: str, n: int = 6) -> list[str]:
    try:
        with DDGS() as ddgs:
            return [r["href"] for r in ddgs.text(query, max_results=n) if r.get("href")]
    except Exception:
        return []


def _fetch(url: str) -> str:
    try:
        response = httpx.get(
            url,
            timeout=20,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (research-agent)"},
        )
        return trafilatura.extract(response.text) or ""
    except Exception:
        return ""


def _relevant(url: str, text: str, app: dict[str, Any], root: str) -> bool:
    if root and root in url.lower():
        return True
    lowered = text.lower()
    key = app["name"].lower().split("(")[0].split()[0]
    keywords = ("api", "oauth", "developer", "endpoint", "token", "sdk", "graphql")
    return key in lowered or any(word in lowered for word in keywords)


def _base_queries(app: dict[str, Any], hint: str) -> list[str]:
    return [
        f"{app['name']} API documentation authentication",
        f"{app['name']} developer {hint} API access",
        f"{app['name']} API pricing free tier developer credentials",
        f"{app['name']} MCP server model context protocol",
    ]


def _composio_payload(
    app: dict[str, Any], hint: str, root: str, extra: list[str] | None = None
) -> dict[str, Any] | None:
    queries = _base_queries(app, hint) + list(extra or [])
    urls: list[str] = []
    for query in queries:
        urls.extend(composio_tools.search(query))
    unique = list(dict.fromkeys(urls))
    unique.sort(key=lambda u: _score(u, root), reverse=True)

    used: list[str] = []
    chunks: list[str] = []
    total = 0
    for url in unique:
        if total >= MAX_CHARS or len(used) >= MAX_PAGES:
            break
        if _is_noise(url):
            continue
        text = composio_tools.scrape(url)
        if not text:
            continue
        used.append(url)
        take = text[: min(PER_PAGE, MAX_CHARS - total)]
        chunks.append(take)
        total += len(take)

    if not chunks:
        return None
    return {"urls": used, "text": "\n\n".join(chunks)[:MAX_CHARS]}


def _local_payload(
    app: dict[str, Any], hint: str, root: str, extra: list[str] | None = None
) -> dict[str, Any]:
    candidates: list[str] = _seeds(hint)
    for query in _base_queries(app, hint) + list(extra or []):
        candidates.extend(_search(query))

    unique = list(dict.fromkeys(candidates))
    unique.sort(key=lambda u: _score(u, root), reverse=True)

    used: list[str] = []
    chunks: list[str] = []
    for allow_noise in (False, True):
        used = []
        chunks = []
        total = 0
        for url in unique:
            if total >= MAX_CHARS or len(used) >= MAX_PAGES:
                break
            if not allow_noise and _is_noise(url):
                continue
            text = _fetch(url)
            if not text:
                continue
            if not allow_noise and not _relevant(url, text, app, root):
                continue
            used.append(url)
            take = text[: min(PER_PAGE, MAX_CHARS - total)]
            chunks.append(take)
            total += len(take)
        if used:
            break

    return {"urls": used, "text": "\n\n".join(chunks)[:MAX_CHARS]}


def retrieve(app: dict[str, Any]) -> dict[str, Any]:
    cached = cache.get(app["id"])
    if cached:
        return cached

    hint = app.get("hint", "")
    root = _host(hint)

    payload = None
    if composio_tools.available():
        try:
            payload = _composio_payload(app, hint, root)
        except Exception:
            payload = None
    if not payload:
        payload = _local_payload(app, hint, root)

    cache.put(app["id"], payload)
    return payload


def retrieve_more(app: dict[str, Any], extra_queries: list[str]) -> dict[str, Any]:
    hint = app.get("hint", "")
    root = _host(hint)

    if composio_tools.available():
        try:
            payload = _composio_payload(app, hint, root, extra=extra_queries)
        except Exception:
            payload = None
        if payload:
            return payload
    return _local_payload(app, hint, root, extra=extra_queries)
