"""Admin & Verification system. Owners: Backend + Admin/Data."""

from fastapi import APIRouter

from app.stubs import not_implemented

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/verify", status_code=204)
def verify_record():
    not_implemented()
