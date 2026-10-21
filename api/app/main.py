import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from psycopg import OperationalError
from psycopg_pool import PoolTimeout

from app.config import settings
from app.routers import academic, admin, announcements, auth, campus, sync

API_PREFIX = "/api/v1"
logger = logging.getLogger(__name__)

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


def _database_unavailable(request: Request, exc: Exception) -> JSONResponse:
    # The real error (which may name a host or SQL) stays in the server log only.
    logger.exception(
        "Database unavailable on %s %s", request.method, request.url.path, exc_info=exc
    )
    return JSONResponse(
        status_code=503,
        content={"detail": "Service temporarily unavailable"},
        headers={"Retry-After": "5"},
    )


for _db_error in (PoolTimeout, OperationalError):
    app.add_exception_handler(_db_error, _database_unavailable)


@app.exception_handler(RequestValidationError)
async def _invalid_input(request: Request, exc: RequestValidationError) -> JSONResponse:
    # FastAPI's default body echoes each bad value back, which would repeat a password or email.
    errors = [{"type": e["type"], "loc": e["loc"], "msg": e["msg"]} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": errors})


@app.middleware("http")
async def _no_store_for_auth(request: Request, call_next):
    # Added here, not in the router, so error responses carry it too.
    response = await call_next(request)
    if request.url.path.startswith(f"{API_PREFIX}/auth"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get(f"{API_PREFIX}/health", tags=["system"])
def get_health() -> dict[str, str]:
    return {"status": "ok"}


# One router module per backend service box in the architecture diagram.
for module in (auth, campus, academic, announcements, admin, sync):
    app.include_router(module.router, prefix=API_PREFIX)
