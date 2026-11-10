"""Similarity-based problem clustering with optional local embedding support.

When OLLAMA_EMBED_MODEL is configured and available, embeddings are used. Otherwise
character n-gram TF-IDF provides a CPU-friendly similarity fallback. The result always
reports its method; TF-IDF is lexical similarity, not a semantic embedding model.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

import numpy as np
import pandas as pd
import requests
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.core.config import OLLAMA_BASE_URL, OLLAMA_EMBED_MODEL, OLLAMA_EMBED_SIMILARITY_THRESHOLD


def _union_find(size: int):
    parent = list(range(size))
    rank = [0] * size
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra == rb:
            return
        if rank[ra] < rank[rb]:
            ra, rb = rb, ra
        parent[rb] = ra
        if rank[ra] == rank[rb]:
            rank[ra] += 1
    return find, union


def _ollama_embeddings(texts: list[str]) -> np.ndarray | None:
    if not OLLAMA_EMBED_MODEL:
        return None
    try:
        output: list[list[float]] = []
        # Keep embedding requests bounded; this is especially important on 6 GB GPUs.
        for start in range(0, len(texts), 24):
            batch = texts[start:start + 24]
            response = requests.post(
                f"{OLLAMA_BASE_URL}/api/embed",
                json={"model": OLLAMA_EMBED_MODEL, "input": batch},
                timeout=90,
            )
            response.raise_for_status()
            vectors = response.json().get("embeddings")
            if not isinstance(vectors, list) or len(vectors) != len(batch):
                return None
            output.extend(vectors)
        matrix = np.asarray(output, dtype=np.float32)
        if matrix.ndim != 2 or not np.isfinite(matrix).all():
            return None
        return matrix
    except (requests.RequestException, ValueError, TypeError):
        return None


def build_problem_clusters(classified: pd.DataFrame, *, threshold: float = 0.76, max_records: int = 2500) -> dict[str, Any]:
    if classified.empty:
        return {"available": False, "reason": "No records are available for clustering.", "clusters": []}
    frame = classified.reset_index(drop=True)
    if len(frame) > max_records:
        return {"available": False, "reason": f"Dataset has {len(frame)} records; clustering is capped at {max_records} records to protect local memory. Analyse smaller batches or raise the configured limit after benchmarking.", "clusters": [], "record_limit": max_records}
    texts = frame["original_feedback"].fillna("").astype(str).tolist()
    if len(texts) < 2:
        return {"available": True, "method": "not_applicable", "threshold": threshold, "clusters": [], "unclustered_records": len(texts)}
    vectors = _ollama_embeddings(texts)
    if vectors is not None:
        matrix = cosine_similarity(vectors)
        method = f"ollama_embeddings:{OLLAMA_EMBED_MODEL}"
        effective_threshold = OLLAMA_EMBED_SIMILARITY_THRESHOLD
    else:
        vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=1, max_features=50000, sublinear_tf=True)
        try:
            matrix = cosine_similarity(vectorizer.fit_transform(texts), dense_output=True)
        except ValueError:
            return {"available": True, "method": "character_ngram_tfidf_fallback", "threshold": threshold, "clusters": [], "clustered_records": 0, "unclustered_records": len(frame), "note": "Text was too short or contained insufficient character patterns for similarity clustering."}
        method = "character_ngram_tfidf_fallback"
        effective_threshold = threshold
    find, union = _union_find(len(texts))
    # Link only pairs inside the same top-level theme to avoid clustering distinct issue categories.
    themes = frame.get("theme", pd.Series(["Other / Unclear"] * len(frame))).astype(str).tolist()
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            if themes[i] == themes[j] and float(matrix[i, j]) >= effective_threshold:
                union(i, j)
    groups: dict[int, list[int]] = {}
    for index in range(len(texts)):
        groups.setdefault(find(index), []).append(index)
    clusters = []
    for members in groups.values():
        if len(members) < 2:
            continue
        member_frame = frame.iloc[members]
        theme = Counter(themes[index] for index in members).most_common(1)[0][0]
        representative_index = max(members, key=lambda index: sum(float(matrix[index, other]) for other in members if other != index))
        clusters.append({
            "cluster_id": f"PC-{len(clusters)+1:03d}",
            "theme": theme,
            "label": texts[representative_index][:120],
            "mention_count": len(members),
            "unique_customers": int(member_frame["source_id"].dropna().astype(str).nunique()) if "source_id" in member_frame else 0,
            "record_ids": member_frame["record_id"].astype(str).tolist(),
            "source_references": member_frame.get("source_reference", pd.Series([None] * len(member_frame))).fillna("").astype(str).tolist(),
            "similarity_basis": method,
        })
    clusters.sort(key=lambda item: (-item["mention_count"], item["theme"], item["cluster_id"]))
    # Stable IDs after sorting.
    for index, cluster in enumerate(clusters, start=1):
        cluster["cluster_id"] = f"PC-{index:03d}"
    clustered = sum(item["mention_count"] for item in clusters)
    return {
        "available": True,
        "method": method,
        "threshold": effective_threshold,
        "clusters": clusters,
        "clustered_records": clustered,
        "unclustered_records": max(0, len(frame) - clustered),
        "note": "Clusters are similarity groups, not proof of a shared technical root cause. TF-IDF fallback measures wording similarity, not deep semantic equivalence.",
    }


def analyze_segments(classified: pd.DataFrame, *, max_categories: int = 12) -> dict[str, Any]:
    if classified.empty:
        return {"available": False, "reason": "No records are available for segmentation.", "dimensions": []}
    candidate_columns = {
        "customer_segment", "segment", "plan", "subscription_plan", "region", "country",
        "device", "platform", "customer_type", "customer_tier", "industry", "language",
    }
    dimensions = []
    for column in classified.columns:
        key = str(column).strip().casefold().replace(" ", "_")
        if key not in candidate_columns:
            continue
        values = classified[column].fillna("").astype(str).str.strip()
        values = values[values.ne("")]
        categories = values.value_counts()
        if len(categories) < 2 or len(categories) > max_categories:
            continue
        groups = []
        for value, count in categories.items():
            subset = classified.loc[classified[column].fillna("").astype(str).str.strip() == value]
            theme_counts = subset["theme"].value_counts()
            groups.append({
                "segment": str(value),
                "feedback_records": int(count),
                "unique_customers": int(subset["source_id"].dropna().astype(str).nunique()) if "source_id" in subset else 0,
                "top_themes": [
                    {"theme": str(theme), "mentions": int(theme_count), "prevalence_pct": round(theme_count / count * 100, 1)}
                    for theme, theme_count in theme_counts.head(5).items()
                ],
            })
        dimensions.append({"column": str(column), "segments": groups})
    return {
        "available": bool(dimensions),
        "dimensions": dimensions,
        "reason": None if dimensions else "No suitable segmentation columns with 2–12 populated categories were found. Add fields such as plan, region, device or customer_segment.",
        "method_note": "Segment prevalence uses feedback-record counts. It is not a customer-level incidence rate unless every record represents one customer and customer IDs are unique.",
    }
