"""Reusable validation helpers for raw dataset values."""

from datetime import datetime, timezone

from .dataset_models import DatasetConfig


def parse_timestamp(value: str) -> datetime | None:
    """Parse only timezone-aware ISO timestamps and normalize them to UTC."""
    text = value.strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def timestamp_in_window(value: datetime, config: DatasetConfig) -> bool:
    """Apply the Version 1 half-open UTC interval."""
    normalized = value.astimezone(timezone.utc)
    return config.start_utc <= normalized < config.end_utc


def parse_conversion(value: str) -> int | None:
    """Accept only literal integer 0 or 1 values, never booleans or fractions."""
    text = value.strip()
    if text not in {"0", "1"}:
        return None
    return int(text)

