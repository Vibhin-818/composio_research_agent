"""Composio Instant retrieval wrapper.

Uses a Composio Session so Instant tools run on Composio's provider accounts
(no Exa/Tavily key). Calls are serialized with a lock because a SDK session is
not safe for concurrent use. A request timeout plus a small circuit breaker
ensure a stalled Composio call degrades to the DuckDuckGo fallback instead of
blocking the run. Loads ``COMPOSIO_API_KEY`` from ``.env`` if present.
"""

import os
import threading
from pathlib import Path
from typing import Any


def _load_env() -> None:
    path = Path(__file__).resolve().parents[1] / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env()

SEARCH_TOOL = os.environ.get("COMPOSIO_SEARCH_TOOL", "EXA_SEARCH")
FETCH_TOOL = os.environ.get("COMPOSIO_FETCH_TOOL", "EXA_GET_CONTENTS_ACTION")
SCRAPE_TOOL = os.environ.get("COMPOSIO_SCRAPE_TOOL", FETCH_TOOL)
USER_ID = os.environ.get("COMPOSIO_USER_ID", "research-agent")
TIMEOUT = float(os.environ.get("COMPOSIO_TIMEOUT", "30"))
MAX_FAILS = int(os.environ.get("COMPOSIO_MAX_FAILS", "3"))
TOOLKITS = [
    toolkit.strip()
    for toolkit in os.environ.get("COMPOSIO_TOOLKITS", "exa").split(",")
    if toolkit.strip()
]

_lock = threading.RLock()
_client = None
_session = None
_broken = False
_fail_count = 0


def _api_key() -> str:
    return os.environ.get("COMPOSIO_API_KEY", "")


def available() -> bool:
    if _broken or not _api_key():
        return False
    try:
        import composio  # noqa: F401
    except Exception:
        return False
    return True


def _get_client():
    global _client
    with _lock:
        if _client is None:
            from composio import Composio

            _client = Composio(api_key=_api_key(), timeout=TIMEOUT, max_retries=2)
    return _client


def _get_session():
    global _session
    with _lock:
        if _session is None:
            _session = _get_client().sessions.create(
                user_id=USER_ID, toolkits=TOOLKITS
            )
    return _session


def _normalize(result: Any) -> Any:
    data = getattr(result, "data", None)
    if data is not None:
        return data
    if hasattr(result, "model_dump"):
        try:
            return result.model_dump()
        except Exception:
            pass
    return result


def _execute(tool: str, arguments: dict[str, Any]) -> Any:
    global _broken, _fail_count
    if _broken:
        raise RuntimeError("Composio disabled after repeated failures")
    with _lock:
        session = _get_session()
        try:
            result = _normalize(session.execute(tool, arguments=arguments))
            _fail_count = 0
            return result
        except Exception as first:
            message = str(first).lower()
            if "account" in message and "not supported" in message:
                try:
                    result = _normalize(
                        session.execute(
                            tool, arguments=arguments, account="instant_account"
                        )
                    )
                    _fail_count = 0
                    return result
                except Exception:
                    pass
            _fail_count += 1
            if _fail_count >= MAX_FAILS:
                _broken = True
            raise first


def _collect_urls(obj: Any) -> list[str]:
    found: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("url", "link", "href") and isinstance(value, str):
                    found.append(value)
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, str) and node.startswith("http"):
            found.append(node)

    walk(obj)
    return list(dict.fromkeys(found))


def _collect_text(obj: Any) -> str:
    def walk(node: Any) -> str:
        if isinstance(node, dict):
            for key in ("markdown", "content", "text", "data"):
                value = node.get(key)
                if isinstance(value, str) and len(value) > 50:
                    return value
            for value in node.values():
                result = walk(value)
                if result:
                    return result
        elif isinstance(node, list):
            for item in node:
                result = walk(item)
                if result:
                    return result
        return ""

    return walk(obj)


def search(query: str, n: int = 6) -> list[str]:
    if not available():
        return []
    for arguments in (
        {"query": query, "numResults": n},
        {"query": query},
    ):
        try:
            result = _execute(SEARCH_TOOL, arguments)
            urls = _collect_urls(result)
            if urls:
                return urls[:n]
        except Exception:
            continue
    return []


def scrape(url: str) -> str:
    if not available():
        return ""
    for arguments in ({"urls": [url]}, {"url": url}):
        try:
            result = _execute(SCRAPE_TOOL, arguments)
            text = _collect_text(result)
            if text:
                return text
        except Exception:
            continue
    return ""
