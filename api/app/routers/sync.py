"""Bulk sync for the offline PWA cache (one request instead of many)."""

from fastapi import APIRouter

from app.stubs import not_implemented

router = APIRouter(prefix="/sync", tags=["sync"])


@router.get("")
def sync(since: str | None = None):
    not_implemented()
