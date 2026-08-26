from datetime import datetime
from typing import Any


def compare_timestamps(
    first_timestamp: datetime,
    second_timestamp: datetime,
) -> dict[str, Any]:
    difference_seconds = (
        second_timestamp - first_timestamp
    ).total_seconds()

    return {
        "first_timestamp": first_timestamp.isoformat(),
        "second_timestamp": second_timestamp.isoformat(),
        "difference_seconds": difference_seconds,
        "difference_direction": (
            "later"
            if difference_seconds > 0
            else "earlier"
            if difference_seconds < 0
            else "same"
        ),
    }
