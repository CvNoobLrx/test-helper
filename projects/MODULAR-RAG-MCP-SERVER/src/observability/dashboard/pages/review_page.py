"""Dashboard page: Review – mastery overview and review planning."""

from __future__ import annotations

import streamlit as st
from pathlib import Path
from typing import Dict, Any, List

from src.core.settings import load_settings, resolve_path
from src.ingestion.storage.knowledge_point_index import KnowledgePointIndex
from src.ingestion.storage.mastery_store import MasteryStore


def render() -> None:
    st.title("Mastery & Review")
    st.markdown("Track your knowledge point mastery and plan review sessions.")

    try:
        settings = load_settings()
    except Exception as e:
        st.error(f"Failed to load settings: {e}")
        return

    # Collection selector
    kp_index = KnowledgePointIndex(
        index_dir=str(resolve_path("data/db/knowledge_points"))
    )

    data_dir = "data/db/mastery"
    if settings.mastery:
        data_dir = settings.mastery.data_dir
    mastery_store = MasteryStore(data_dir=str(resolve_path(data_dir)))

    # Discover collections from KP index
    collections_dir = resolve_path("data/db/knowledge_points")
    collections = []
    if collections_dir.exists():
        for f in collections_dir.iterdir():
            if f.suffix == ".json" and f.stem.endswith("_kp"):
                collections.append(f.stem.replace("_kp", ""))

    if not collections:
        st.info("No knowledge points found. Ingest documents first to extract knowledge points.")
        return

    collection = st.sidebar.selectbox("Collection", collections, key="review_collection")

    # Load data
    all_kps = kp_index.get_by_collection(collection)
    all_records = mastery_store.get_all_records(collection)
    record_map = {r.knowledge_point_id: r for r in all_records}

    if not all_kps:
        st.info(f"No knowledge points in collection '{collection}'.")
        return

    # Categorize
    mastered = []
    learning = []
    needs_review = []

    for kp in all_kps:
        rec = record_map.get(kp["id"])
        if rec is None or rec.review_count == 0:
            needs_review.append(kp)
        elif rec.correct_rate >= 0.8:
            mastered.append(kp)
        elif rec.correct_rate >= 0.5:
            learning.append(kp)
        else:
            needs_review.append(kp)

    total = len(all_kps)

    # Overview metrics
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total KPs", total)
    col2.metric("Mastered", f"{len(mastered)} ({len(mastered)*100//max(total,1)}%)")
    col3.metric("Learning", f"{len(learning)} ({len(learning)*100//max(total,1)}%)")
    col4.metric("Needs Review", f"{len(needs_review)} ({len(needs_review)*100//max(total,1)}%)")

    # Progress bar
    st.subheader("Progress")
    if total > 0:
        mastered_pct = len(mastered) / total
        learning_pct = len(learning) / total
        st.progress(mastered_pct, text=f"Mastered: {mastered_pct*100:.1f}%")

    # Category breakdown
    st.subheader("By Category")
    categories: Dict[str, Dict[str, int]] = {}
    for kp in all_kps:
        cat = kp.get("category", "general")
        if cat not in categories:
            categories[cat] = {"total": 0, "mastered": 0, "learning": 0, "needs_review": 0}
        categories[cat]["total"] += 1

        rec = record_map.get(kp["id"])
        if rec is None or rec.review_count == 0:
            categories[cat]["needs_review"] += 1
        elif rec.correct_rate >= 0.8:
            categories[cat]["mastered"] += 1
        elif rec.correct_rate >= 0.5:
            categories[cat]["learning"] += 1
        else:
            categories[cat]["needs_review"] += 1

    for cat, stats in sorted(categories.items()):
        with st.expander(f"{cat} ({stats['total']} KPs)"):
            c1, c2, c3 = st.columns(3)
            c1.metric("Mastered", stats["mastered"])
            c2.metric("Learning", stats["learning"])
            c3.metric("Needs Review", stats["needs_review"])

    # Knowledge point tree
    st.subheader("Knowledge Points")
    filter_category = st.selectbox(
        "Filter by category",
        ["All"] + sorted(categories.keys()),
        key="review_filter_cat",
    )

    display_kps = all_kps
    if filter_category != "All":
        display_kps = [kp for kp in all_kps if kp.get("category") == filter_category]

    for kp in display_kps:
        rec = record_map.get(kp["id"])
        if rec and rec.review_count > 0:
            rate = f"{rec.correct_rate*100:.0f}%"
            interval = f"{rec.interval_days}d"
            icon = "green" if rec.correct_rate >= 0.8 else ("orange" if rec.correct_rate >= 0.5 else "red")
        else:
            rate = "New"
            interval = "-"
            icon = "gray"

        st.markdown(
            f":{icon}[●] **{kp['text']}** "
            f"(`{kp.get('category', '')}` | mastery: {rate} | interval: {interval})"
        )
