import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import yaml

from agent import cache, composio_tools, extract, retrieve, verify
from config import APPS_FILE, MAX_CONCURRENCY, MODEL, RESULTS
from schema import AppRecord, AppResearch

EXTRACTION_ATTEMPTS = 2


def _gaps(research: AppResearch) -> list[str]:
    gaps: list[str] = []
    auth = set(research.auth_methods or [])
    if not auth or auth <= {"Unknown"}:
        gaps.append("authentication")
    if research.access in ("unknown", None, ""):
        gaps.append("access")
    if research.api_type in ("unknown", None, "") or not research.api_documented:
        gaps.append("api")
    if research.mcp in ("unknown", None, ""):
        gaps.append("mcp")
    return gaps


def _gap_queries(app: dict[str, Any], gaps: list[str]) -> list[str]:
    name = app["name"]
    mapping = {
        "authentication": f"{name} API authentication OAuth API key how to get credentials",
        "access": f"{name} API pricing free tier sign up developer account",
        "api": f"{name} REST GraphQL API reference documentation",
        "mcp": f"{name} MCP server model context protocol",
    }
    return [mapping[gap] for gap in gaps if gap in mapping][:3]


def _extract_with_retry(
    app: dict[str, Any], docs: dict[str, Any]
) -> AppResearch:
    failures: list[str] = []
    for attempt in range(1, EXTRACTION_ATTEMPTS + 1):
        try:
            return extract.extract(app, docs)
        except Exception as exc:
            failures.append(f"attempt {attempt}: {type(exc).__name__}: {exc}")
            if attempt < EXTRACTION_ATTEMPTS:
                time.sleep(1)
    raise RuntimeError(
        f"NVIDIA extraction failed after {EXTRACTION_ATTEMPTS} attempts: "
        + " | ".join(failures)
    )


def _needs_review_record(
    app: dict[str, Any], reason: str, docs: dict[str, Any] | None = None
) -> AppRecord:
    research = AppResearch(
        name=app["name"],
        category=app["category"],
        one_liner="Research extraction failed; manual review required.",
        blocker="See the SQLite manual_review queue for the failure details.",
        evidence_urls=(docs or {}).get("urls", []),
    )
    return AppRecord(
        id=app["id"],
        status="needs-human",
        research=research,
        verification={
            "supported": False,
            "issues": [reason],
            "confidence": 0.0,
            "gaps": ["research"],
        },
        error=reason,
    )


def process(app: dict[str, Any]) -> AppRecord:
    docs = retrieve.retrieve(app)
    try:
        research = _extract_with_retry(app, docs)
    except Exception as exc:
        return _needs_review_record(app, str(exc), docs)

    first_pass_research = research.model_copy(deep=True)
    gaps = _gaps(research)
    supplemental_failures: list[str] = []
    if gaps and (research.confidence or 0) < 0.8:
        try:
            extra = retrieve.retrieve_more(app, _gap_queries(app, gaps))
        except Exception as exc:
            extra = {}
            supplemental_failures.append(f"Gap-fill retrieval failed: {exc}")
        if extra.get("text"):
            docs = {
                "urls": list(
                    dict.fromkeys(
                        list(docs.get("urls", [])) + list(extra.get("urls", []))
                    )
                ),
                "text": (docs.get("text", "") + "\n\n" + extra["text"])[
                    : retrieve.MAX_CHARS
                ],
            }
            try:
                research = _extract_with_retry(app, docs)
            except Exception as exc:
                supplemental_failures.append(f"Gap-fill extraction failed: {exc}")

    check = verify.verify(app, research, docs)
    check["gaps"] = gaps
    if supplemental_failures:
        check.setdefault("issues", []).extend(supplemental_failures)
        check["supported"] = False
    status = "ok" if check.get("supported") else "needs-human"
    return AppRecord(
        id=app["id"],
        status=status,
        research=research,
        first_pass_research=first_pass_research,
        verification=check,
    )


def _write(results: dict[int, dict[str, Any]], apps: list[dict[str, Any]]) -> None:
    ordered = [results[a["id"]] for a in apps if a["id"] in results]
    temp_path = RESULTS.with_suffix(f"{RESULTS.suffix}.tmp")
    temp_path.write_text(
        json.dumps(ordered, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    temp_path.replace(RESULTS)


def _select(
    apps: list[dict[str, Any]], limit: int | None, ids: str | None
) -> list[dict[str, Any]]:
    if ids:
        wanted = {int(x) for x in ids.split(",") if x.strip()}
        known = {app["id"] for app in apps}
        unknown = wanted - known
        if unknown:
            raise ValueError(
                f"Unknown app id(s): {', '.join(map(str, sorted(unknown)))}"
            )
        return [app for app in apps if app["id"] in wanted]
    if limit is not None:
        if limit < 1:
            raise ValueError("--limit must be a positive integer")
        return apps[:limit]
    return apps


def main() -> None:
    parser = argparse.ArgumentParser(description="Research apps with the NVIDIA API.")
    parser.add_argument("--limit", type=int, default=None, help="Only the first N apps.")
    parser.add_argument("--ids", type=str, default=None, help="Comma-separated app ids.")
    args = parser.parse_args()

    cache.init()
    all_apps = yaml.safe_load(APPS_FILE.read_text(encoding="utf-8"))
    try:
        targets = _select(all_apps, args.limit, args.ids)
    except ValueError as exc:
        parser.error(str(exc))

    results = cache.load_results()
    if RESULTS.exists():
        for rec in json.loads(RESULTS.read_text(encoding="utf-8")):
            if rec["id"] not in results:
                results[rec["id"]] = rec
                cache.save_result(rec)

    total = len(targets)
    backend = (
        "Composio Instant (EXA_SEARCH + EXA_GET_CONTENTS_ACTION)"
        if composio_tools.available()
        else "DuckDuckGo fallback"
    )
    print(
        f"Running {total} app(s) with model {MODEL} | retrieval: {backend}",
        flush=True,
    )

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENCY) as pool:
        futures = {pool.submit(process, app): app for app in targets}
        completed = 0
        for future in as_completed(futures):
            app = futures[future]
            try:
                record = future.result()
            except Exception as exc:
                record = _needs_review_record(
                    app, f"Pipeline failed: {type(exc).__name__}: {exc}"
                )
            result = record.model_dump()
            cache.save_result(result)
            results[record.id] = result
            _write(results, all_apps)
            completed += 1
            print(f"[{completed}/{total}] app {record.id} -> {record.status}", flush=True)

    _write(results, all_apps)
    print(f"Done. Wrote {RESULTS}", flush=True)


if __name__ == "__main__":
    main()
