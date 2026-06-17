"""Scoped HTTP client for the mock procurement API.

All supplier-scoped calls inject the configured SUPPLIER_ID here.
The model never sees or controls supplier_id.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from agent.config import API_BASE_URL, SUPPLIER_ID


class ProcurementApiError(RuntimeError):
    """Raised when the procurement API returns an error."""


def _clean_params(params: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in params.items() if value is not None}


def _handle_response(response: httpx.Response) -> str:
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        payload = {
            "error": "api_error",
            "status_code": exc.response.status_code,
            "detail": exc.response.text,
        }
        return json.dumps(payload)
    return response.text


def get(path: str, *, params: dict[str, Any] | None = None, scoped: bool = True) -> str:
    query = _clean_params(params or {})
    if scoped:
        query["supplier_id"] = SUPPLIER_ID
    response = httpx.get(f"{API_BASE_URL}{path}", params=query, timeout=10.0)
    return _handle_response(response)


def post(
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    scoped: bool = True,
) -> str:
    query = _clean_params(params or {})
    if scoped:
        query["supplier_id"] = SUPPLIER_ID
    response = httpx.post(
        f"{API_BASE_URL}{path}",
        params=query,
        json=_clean_params(json_body or {}),
        timeout=10.0,
    )
    return _handle_response(response)