from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.config import settings
from app.routers import academic, admin, announcements, auth, campus, sync

API_PREFIX = "/api/v1"

app = FastAPI(
    title="FUTA Fresher Companion API",
    version="0.1.0",
    docs_url=f"{API_PREFIX}/docs",
    openapi_url=f"{API_PREFIX}/openapi.json",
)

# Low-data requirement: compress every response above 500 bytes.
app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get(f"{API_PREFIX}/health", tags=["system"])
def get_health() -> dict[str, str]:
    return {"status": "ok"}


# One router module per backend service box in the architecture diagram.
for module in (auth, campus, academic, announcements, admin, sync):
    app.include_router(module.router, prefix=API_PREFIX)
