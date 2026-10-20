"""Cache-Control for public GET responses that are the same for every caller."""

from fastapi import Response

PUBLIC_CACHE_CONTROL = "public, max-age=60, s-maxage=300, stale-while-revalidate=600"


def public_cache(response: Response) -> None:
    """FastAPI dependency. Use only on public reads. Never on auth or user-specific routes."""
    response.headers["Cache-Control"] = PUBLIC_CACHE_CONTROL
