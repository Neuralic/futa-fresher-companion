"""User & Auth service. Owner: Backend."""

from fastapi import APIRouter

from app.stubs import not_implemented

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=201)
def register():
    not_implemented()


@router.post("/login")
def login():
    not_implemented()


@router.get("/me")
def me():
    not_implemented()
