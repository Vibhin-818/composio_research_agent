"""Unsupervised clustering for the 100-app dataset.

Builds a one-hot capability matrix (access, buildability, API type/breadth, MCP,
auth methods, confidence) and runs k-means++ with a silhouette-based choice of k.
Pure numpy so the repo stays dependency-light and reproducible (fixed seed).
"""

from typing import Any

import numpy as np
import pandas as pd

ACCESS = [
    "self-serve",
    "free-tier",
    "paid-plan",
    "admin-approval",
    "contact-sales",
    "partner",
    "unknown",
]
BUILD = ["yes", "with-work", "no", "unknown"]
API = ["REST", "GraphQL", "both", "none", "unknown"]
BREADTH = ["small", "medium", "broad", "unknown"]
MCP = ["none", "official", "community", "unknown"]
AUTH = [
    "OAuth2",
    "API key",
    "Basic",
    "Bearer token",
    "Personal access token",
    "JWT",
    "Signed request",
    "Other",
    "Unknown",
]

SEED = 42


def build_features(df: pd.DataFrame) -> tuple[np.ndarray, list[str]]:
    cols: list[np.ndarray] = []
    names: list[str] = []
    for col, values, prefix in (
        ("access", ACCESS, "access"),
        ("buildability", BUILD, "build"),
        ("api_type", API, "api"),
        ("api_breadth", BREADTH, "breadth"),
        ("mcp", MCP, "mcp"),
    ):
        for value in values:
            cols.append((df[col] == value).astype(float).to_numpy())
            names.append(f"{prefix}={value}")
    for method in AUTH:
        cols.append(
            df["auth"].apply(lambda xs, m=method: float(m in xs)).to_numpy()
        )
        names.append(f"auth={method}")
    cols.append(df["confidence"].clip(0, 1).to_numpy(dtype=float))
    names.append("confidence")
    return np.column_stack(cols).astype(float), names


def _init_centers(X: np.ndarray, k: int, rng: np.random.Generator) -> np.ndarray:
    n = len(X)
    centers = [X[rng.integers(n)]]
    for _ in range(1, k):
        dist = np.min(
            ((X[:, None, :] - np.array(centers)[None, :, :]) ** 2).sum(axis=2),
            axis=1,
        )
        total = float(dist.sum())
        probs = dist / total if total > 0 else np.full(n, 1.0 / n)
        centers.append(X[rng.choice(n, p=probs)])
    return np.array(centers)


def _kmeans(X: np.ndarray, k: int, rng: np.random.Generator, n_init: int = 10, max_iter: int = 100):
    best = None
    for _ in range(n_init):
        centers = _init_centers(X, k, rng)
        labels = np.zeros(len(X), dtype=int)
        for _ in range(max_iter):
            dist = ((X[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
            new = dist.argmin(axis=1)
            if np.array_equal(new, labels):
                break
            labels = new
            for c in range(k):
                if (labels == c).any():
                    centers[c] = X[labels == c].mean(axis=0)
        inertia = float(((X - centers[labels]) ** 2).sum())
        if best is None or inertia < best[0]:
            best = (inertia, labels.copy(), centers.copy())
    return best[1], best[2], best[0]


def _silhouette(X: np.ndarray, labels: np.ndarray) -> float:
    n = len(X)
    unique = np.unique(labels)
    if n < 2 or len(unique) < 2:
        return 0.0
    dist = np.linalg.norm(X[:, None, :] - X[None, :, :], axis=2)
    scores = np.zeros(n)
    for i in range(n):
        same = labels == labels[i]
        a = dist[i, same].sum() / (same.sum() - 1) if same.sum() > 1 else 0.0
        b = min(dist[i, labels == c].mean() for c in unique if c != labels[i])
        denom = max(a, b)
        scores[i] = (b - a) / denom if denom > 0 else 0.0
    return float(scores.mean())


def _label(sub: pd.DataFrame) -> str:
    if sub.empty:
        return "unknown"
    access = sub["access"].mode().iloc[0]
    build = sub["buildability"].mode().iloc[0]
    api = sub["api_type"].mode().iloc[0]
    mcp = sub["mcp"].mode().iloc[0]
    parts = [str(access), str(build)]
    if api != "unknown":
        parts.append(str(api))
    if mcp in ("official", "community"):
        parts.append(f"{mcp} MCP")
    return " · ".join(parts)


def ml_cluster(df: pd.DataFrame) -> dict[str, Any] | None:
    n = len(df)
    if n < 4:
        return None

    X, names = build_features(df)
    rng = np.random.default_rng(SEED)

    best = None
    for k in range(2, min(6, n - 1) + 1):
        labels, centers, inertia = _kmeans(X, k, rng)
        if len(np.unique(labels)) < 2:
            continue
        score = _silhouette(X, labels)
        if best is None or score > best["silhouette"]:
            best = {
                "k": k,
                "silhouette": score,
                "labels": labels,
                "inertia": inertia,
            }
    if best is None:
        return None

    labels = best["labels"]
    clusters = []
    for c in sorted(np.unique(labels).tolist()):
        mask = labels == c
        sub = df[mask]
        members = [x for x in sub["id"].tolist() if x is not None]
        clusters.append(
            {
                "id": int(c),
                "size": int(mask.sum()),
                "label": _label(sub),
                "members": sorted(int(x) for x in members),
            }
        )
    clusters.sort(key=lambda item: item["size"], reverse=True)

    return {
        "method": "k-means++ on one-hot capability features",
        "seed": SEED,
        "k": int(best["k"]),
        "silhouette": round(float(best["silhouette"]), 3),
        "inertia": round(float(best["inertia"]), 3),
        "features": names,
        "clusters": clusters,
    }
