"""Fails if the implemented routes drift from docs/openapi.yaml (the frozen contract)."""

import pathlib

import yaml

from app.main import app

SPEC_PATH = pathlib.Path(__file__).resolve().parents[2] / "docs" / "openapi.yaml"
SPEC = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))
PREFIX = SPEC["servers"][0]["url"].rstrip("/")
METHODS = {"get", "post", "put", "patch", "delete"}


def _spec_ops() -> set[tuple[str, str]]:
    return {
        (method.upper(), PREFIX + path)
        for path, item in SPEC["paths"].items()
        for method in item
        if method in METHODS
    }


def _app_ops() -> set[tuple[str, str]]:
    return {
        (method.upper(), path)
        for path, item in app.openapi()["paths"].items()
        for method in item
        if method in METHODS
    }


def test_every_spec_operation_is_implemented():
    missing = sorted(_spec_ops() - _app_ops())
    assert not missing, f"In docs/openapi.yaml but missing from the API: {missing}"


def test_no_undocumented_operations():
    extra = sorted(_app_ops() - _spec_ops())
    assert not extra, (
        f"Implemented but not in docs/openapi.yaml: {extra}. "
        "Update the contract first (needs lead approval)."
    )
