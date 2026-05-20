from __future__ import annotations


CHANNELS = ("CH1", "CH2", "CH3")


def normalize_channel(channel: str | int) -> str:
    """Return a validated Keysight channel label like CH1."""
    if isinstance(channel, int):
        value = f"CH{channel}"
    else:
        raw = str(channel).strip().upper()
        value = raw if raw.startswith("CH") else f"CH{raw}"

    if value not in CHANNELS:
        raise ValueError(f"Invalid channel {channel!r}; expected CH1, CH2, or CH3")
    return value


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
