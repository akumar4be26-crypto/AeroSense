"""Logging setup. Precise coordinates are never written to logs."""
from __future__ import annotations

import logging


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def coarse_location(lat: float, lon: float) -> str:
    """Return a ~11 km resolution label for logs instead of precise coordinates."""
    return f"~{lat:.1f},{lon:.1f}"
