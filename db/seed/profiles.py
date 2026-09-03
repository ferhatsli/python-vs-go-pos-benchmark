from __future__ import annotations

SEED = 20260831

PROFILES: dict[str, dict[str, int]] = {
    "D1": {"companies": 10, "stations": 50, "devices": 500, "payments": 100_000},
    "D2": {"companies": 50, "stations": 500, "devices": 5_000, "payments": 1_000_000},
    "D3": {"companies": 500, "stations": 5_000, "devices": 50_000, "payments": 1_000_000},
}


def get_profile(name: str) -> dict[str, int]:
    try:
        return PROFILES[name]
    except KeyError as exc:
        raise ValueError(f"unknown profile: {name}") from exc
