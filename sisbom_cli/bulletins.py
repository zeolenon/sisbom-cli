"""Normalize regular bulletin numbers without conflating addenda."""
import re


def normalize_regular_bg_number(label: str | None) -> str | None:
    if not isinstance(label, str):
        return None
    match = re.fullmatch(r"(?:BG\s+)?(\d{1,3})\.?", label.strip(), re.IGNORECASE)
    return match.group(1).zfill(3) if match else None
