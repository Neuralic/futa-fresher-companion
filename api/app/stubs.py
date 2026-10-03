from typing import NoReturn

from fastapi import HTTPException


def not_implemented() -> NoReturn:
    """Placeholder for endpoints defined in docs/openapi.yaml but not built yet.

    Replace the call with a real implementation. Do NOT change the route path/method
    here without changing docs/openapi.yaml first (lead approval needed).
    """
    raise HTTPException(status_code=501, detail="Not implemented yet")
