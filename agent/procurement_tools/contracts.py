"""Contract tools.

Available API endpoints:
  GET  /contracts            — List/filter contracts (params: supplier_id, status, expiring_within_days)
  GET  /contracts/{id}       — Get a single contract by ID (params: supplier_id)
"""

from typing import Optional
import agent.api_client as api_client


GET_CONTRACTS_SCHEMA = {
    "type": "function",
    "name": "get_contracts",
    "description": "Retrieve contracts. Use this to check contract statuses, find expiring contracts, or review contract details.",
    "parameters": {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["active", "expired", "pending_renewal"],
                "description": "Filter contracts by status.",
            },
            "expiring_within_days": {
                "type": "integer",
                "description": "Filter to show only contracts expiring within N days from today (minimum 1).",
            },
        },
        "required": [],
    },
}


def get_contracts(
    status: Optional[str] = None,
    expiring_within_days: Optional[int] = None,
) -> str:
    """Fetch contracts from the procurement API, optionally filtered."""
    params = {
        "status": status,
        "expiring_within_days": expiring_within_days,
    }
    return api_client.get("/contracts", params=params)
