"""Campus service (buildings, map, routing). Owners: Backend + Maps/GIS."""

from fastapi import APIRouter

from app.stubs import not_implemented

router = APIRouter(prefix="/campus", tags=["campus"])


@router.get("/buildings")
def list_buildings(q: str | None = None, type: str | None = None, limit: int = 50, offset: int = 0):
    not_implemented()


@router.get("/buildings/{building_id}")
def get_building(building_id: str):
    not_implemented()


@router.get("/route")
def get_route(from_lat: float, from_lng: float, to_building_id: str):
    not_implemented()
