"""Information service (announcements & updates)."""

from fastapi import APIRouter

from app.stubs import not_implemented

router = APIRouter(prefix="/announcements", tags=["announcements"])


@router.get("")
def list_announcements(
    scope: str | None = None,
    faculty_id: str | None = None,
    department_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    not_implemented()


@router.get("/{announcement_id}")
def get_announcement(announcement_id: str):
    not_implemented()


@router.post("", status_code=201)
def create_announcement():
    not_implemented()
