import json
import time
from collections import Counter

import pandas as pd

from agent.cluster import ml_cluster
from config import PATTERNS, RESULTS


def _load(path):
    last_error = None
    for _ in range(5):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(0.5)
    raise RuntimeError(f"Unable to read valid JSON from {path}") from last_error


def _cluster(row) -> str:
    access = row["access"]
    build = row["buildability"]
    if access in ("admin-approval", "contact-sales", "partner"):
        return "needs-outreach"
    if build == "no":
        return "blocked"
    if access in ("self-serve", "free-tier") and build == "yes":
        return "easy-win"
    if access in ("self-serve", "free-tier"):
        return "easy-access"
    return "with-work"


def _blocker_theme(value: str) -> str:
    text = value.casefold()
    if any(
        term in text
        for term in ("no public api", "limited public api", "mcp server not officially")
    ):
        return "API/MCP surface gaps"
    if any(
        term in text
        for term in (
            "approval",
            "partner",
            "contact sales",
            "sales negotiation",
            "contract",
            "admin",
        )
    ):
        return "Approval or partner gates"
    if any(term in text for term in ("rate limit", "security", "role-based", "permission")):
        return "Permissions, security or rate limits"
    if any(
        term in text
        for term in (
            "oauth",
            "token",
            "api key",
            "credential",
            "service account",
            "connectionid",
            "auth",
            "setup",
            "scope",
        )
    ):
        return "Authentication or setup"
    return "Other / unclear"


def _rows(data) -> list[dict]:
    rows = []
    for record in data:
        research = record.get("research") or {}
        rows.append(
            {
                "id": record.get("id"),
                "status": record.get("status", "unknown"),
                "category": research.get("category", "unknown"),
                "access": research.get("access", "unknown"),
                "buildability": research.get("buildability", "unknown"),
                "api_type": research.get("api_type", "unknown"),
                "api_breadth": research.get("api_breadth", "unknown"),
                "mcp": research.get("mcp", "unknown"),
                "confidence": research.get("confidence") or 0.0,
                "auth": research.get("auth_methods") or [],
                "blocker": (research.get("blocker") or "").strip(),
            }
        )
    return rows


def main() -> None:
    data = _load(RESULTS)
    rows = _rows(data)

    if not rows:
        PATTERNS.write_text(
            json.dumps({"total": 0, "clusters": [], "summary": {}}, indent=2),
            encoding="utf-8",
        )
        print(f"Wrote {PATTERNS} (no rows yet)")
        return

    df = pd.DataFrame(rows)
    df["cluster"] = df.apply(_cluster, axis=1)

    auth = Counter(method for methods in df["auth"] for method in methods)
    access = Counter(df["access"])
    build = Counter(df["buildability"])
    mcp = Counter(df["mcp"])
    categories = Counter(df["category"])
    statuses = Counter(df["status"])
    clusters = Counter(df["cluster"])
    blockers = Counter(blocker for blocker in df["blocker"] if blocker)
    blocker_themes = Counter(
        _blocker_theme(value) for value in df["blocker"] if value
    )

    by_category_access: dict[str, dict[str, int]] = {}
    for category, group in df.groupby("category"):
        by_category_access[str(category)] = {
            str(tier): int(count) for tier, count in group["access"].value_counts().items()
        }

    cluster_members: dict[str, list[int]] = {}
    for cluster in clusters:
        ids = [x for x in df[df["cluster"] == cluster]["id"].tolist() if x is not None]
        cluster_members[str(cluster)] = sorted(int(x) for x in ids)

    ml = None
    try:
        ml = ml_cluster(df)
    except Exception as exc:
        print(f"ML clustering skipped: {exc}")

    summary = {
        "avg_confidence": round(float(df["confidence"].mean()), 3),
        "ok_rate": round(float((df["status"] == "ok").mean()), 3),
        "mcp_coverage": round(
            float(df["mcp"].isin(["official", "community"]).mean()), 3
        ),
        "self_serve_or_free": int(df["access"].isin(["self-serve", "free-tier"]).sum()),
        "gated_access": int((~df["access"].isin(["self-serve", "free-tier"])).sum()),
        "mcp_confirmed": int(df["mcp"].isin(["official", "community"]).sum()),
        "mcp_unknown": int((df["mcp"] == "unknown").sum()),
        "mcp_none": int((df["mcp"] == "none").sum()),
        "apps_with_blockers": int(df["blocker"].astype(bool).sum()),
        "easy_wins": int(clusters.get("easy-win", 0)),
        "needs_outreach": int(clusters.get("needs-outreach", 0)),
        "max_exact_blocker_count": max(blockers.values(), default=0),
    }

    patterns = {
        "total": int(len(df)),
        "auth": auth.most_common(),
        "access": access.most_common(),
        "buildability": build.most_common(),
        "mcp": mcp.most_common(),
        "categories": categories.most_common(),
        "statuses": statuses.most_common(),
        "top_blockers": blockers.most_common(10),
        "blocker_themes": blocker_themes.most_common(),
        "by_category_access": by_category_access,
        "clusters": clusters.most_common(),
        "cluster_members": cluster_members,
        "ml_clusters": ml,
        "summary": summary,
    }

    PATTERNS.write_text(
        json.dumps(patterns, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    extra = f", k-means k={ml['k']} sil={ml['silhouette']}" if ml else ", k-means skipped"
    print(f"Wrote {PATTERNS} ({len(df)} apps, {len(clusters)} segments{extra})")


if __name__ == "__main__":
    main()
