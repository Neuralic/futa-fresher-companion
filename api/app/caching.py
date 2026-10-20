"""Cache-Control for public GET responses that are the same for every caller."""

from fastapi import Response

PUBLIC_CACHE_CONTROL = "public, max-age=60, s-maxage=300, stale-while-revalidate=600"


def public_cache(response: Response) -> None:
    """FastAPI dependency. Use only on public reads. Never on auth or user-specific routes."""
    response.headers["Cache-Control"] = PUBLIC_CACHE_CONTROL


# For public reads that carry personal data (NDPR). Shared caches may keep them 30s at most.
SHORT_CACHE_CONTROL = "public, max-age=0, s-maxage=30, must-revalidate"


def short_public_cache(response: Response) -> None:
    """FastAPI dependency. Use only for public reads that carry personal data."""
    response.headers["Cache-Control"] = SHORT_CACHE_CONTROL


# For public, time-sensitive reads: an announcement that is published or expires must show up fast.
FRESH_CACHE_CONTROL = "public, max-age=0, s-maxage=30, stale-while-revalidate=60"


def fresh_public_cache(response: Response) -> None:
    """FastAPI dependency. Use only for public reads whose rows change with time."""
    response.headers["Cache-Control"] = FRESH_CACHE_CONTROL
