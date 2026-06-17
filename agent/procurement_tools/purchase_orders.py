"""Purchase Order tools.

Available API endpoints:
  GET  /purchase-orders            — List/filter purchase orders (params: supplier_id, status, created_after, created_before, min_amount)
  GET  /purchase-orders/{po_id}    — Get a single purchase order by ID (params: supplier_id)
  POST /purchase-orders/{po_id}/acknowledge — Acknowledge a purchase order (params: supplier_id)
"""

from typing import Optional
import agent.api_client as api_client


GET_PURCHASE_ORDERS_SCHEMA = {
    "type": "function",
    "name": "get_purchase_orders",
    "description": "Retrieve purchase orders. Use this to check order statuses, find orders by date range, or review order history.",
    "parameters": {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["submitted", "acknowledged"],
                "description": "Filter purchase orders by status.",
            },
            "created_after": {
                "type": "string",
                "description": "Filter to show only purchase orders created after this date (format: YYYY-MM-DD).",
            },
            "created_before": {
                "type": "string",
                "description": "Filter to show only purchase orders created before this date (format: YYYY-MM-DD).",
            },
            "min_amount": {
                "type": "number",
                "description": "Minimum purchase order amount to filter by.",
            },
        },
        "required": [],
    },
}


GET_PURCHASE_ORDER_SCHEMA = {
    "type": "function",
    "name": "get_purchase_order",
    "description": "Retrieve a single purchase order by its ID.",
    "parameters": {
        "type": "object",
        "properties": {
            "po_id": {
                "type": "integer",
                "description": "The unique identifier of the purchase order to retrieve.",
            },
        },
        "required": ["po_id"],
    },
}


ACKNOWLEDGE_PURCHASE_ORDER_SCHEMA = {
    "type": "function",
    "name": "acknowledge_purchase_order",
    "description": "Acknowledge a submitted purchase order. This transitions the status from 'submitted' to 'acknowledged'.",
    "parameters": {
        "type": "object",
        "properties": {
            "po_id": {
                "type": "integer",
                "description": "The unique identifier of the purchase order to acknowledge.",
            },
        },
        "required": ["po_id"],
    },
}


def get_purchase_orders(
    status: Optional[str] = None,
    created_after: Optional[str] = None,
    created_before: Optional[str] = None,
    min_amount: Optional[float] = None,
) -> str:
    """Fetch purchase orders from the procurement API, optionally filtered."""
    params = {
        "status": status,
        "created_after": created_after,
        "created_before": created_before,
        "min_amount": min_amount,
    }
    return api_client.get("/purchase-orders", params=params)


def get_purchase_order(po_id: int) -> str:
    """Fetch a single purchase order by ID from the procurement API."""
    return api_client.get(f"/purchase-orders/{po_id}")


def acknowledge_purchase_order(po_id: int) -> str:
    """Acknowledge a submitted purchase order, transitioning it from 'submitted' to 'acknowledged'."""
    return api_client.post(f"/purchase-orders/{po_id}/acknowledge")
