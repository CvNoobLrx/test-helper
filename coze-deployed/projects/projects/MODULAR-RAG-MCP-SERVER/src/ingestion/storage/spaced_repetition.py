"""SM-2 Spaced Repetition Algorithm.

Pure functions for calculating next review intervals based on the
SuperMemo SM-2 algorithm. No I/O, easy to unit test.

Reference: https://supermemo.guru/wiki/SM-2_algorithm
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from src.core.types import MasteryRecord
from src.observability.logger import get_logger

logger = get_logger(__name__)

# Default constants
DEFAULT_EASE_FACTOR = 2.5
MIN_EASE_FACTOR = 1.3


def calculate_next_review(
    quality: int,
    record: MasteryRecord,
    min_ease_factor: float = MIN_EASE_FACTOR,
    now: Optional[datetime] = None,
) -> MasteryRecord:
    """Calculate the next review time using SM-2 algorithm.

    Args:
        quality: Recall quality score 0-5
            0 - Complete blackout
            1 - Incorrect, but upon seeing the answer, remembered
            2 - Incorrect, but the answer seemed easy to recall
            3 - Correct with serious difficulty
            4 - Correct after hesitation
            5 - Perfect response
        record: Current mastery record
        min_ease_factor: Minimum ease factor (default 1.3)
        now: Current time (for testing; defaults to utcnow)

    Returns:
        Updated MasteryRecord with new interval, ease_factor, and next_review_time
    """
    if not 0 <= quality <= 5:
        raise ValueError(f"Quality must be 0-5, got {quality}")

    if now is None:
        now = datetime.now(timezone.utc)

    new_review_count = record.review_count + 1
    new_correct_count = record.correct_count + (1 if quality >= 3 else 0)
    new_correct_rate = new_correct_count / new_review_count if new_review_count > 0 else 0.0

    ease_factor = record.ease_factor
    interval = record.interval_days

    if quality >= 3:
        # Correct recall
        if record.review_count == 0:
            interval = 1
        elif record.review_count == 1:
            interval = 6
        else:
            interval = round(interval * ease_factor)

        # Update ease factor
        ease_factor = ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
        if ease_factor < min_ease_factor:
            ease_factor = min_ease_factor
    else:
        # Incorrect recall - reset interval
        interval = 1

    next_review = now + timedelta(days=interval)

    return MasteryRecord(
        knowledge_point_id=record.knowledge_point_id,
        collection=record.collection,
        review_count=new_review_count,
        correct_count=new_correct_count,
        correct_rate=round(new_correct_rate, 3),
        ease_factor=round(ease_factor, 2),
        interval_days=interval,
        last_review_time=now.isoformat(),
        next_review_time=next_review.isoformat(),
    )
