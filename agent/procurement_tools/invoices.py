"""Invoice tools — fully implemented as a reference example.

Available API endpoints:
  GET  /invoices            — List/filter invoices (params: supplier_id, status, overdue, min_amount, max_amount)
  GET  /invoices/{id}       — Get a single invoice by ID (params: supplier_id)
  POST /invoices            — Create a new invoice (query: supplier_id required, body: po_id, amount, due_date, currency)
"""

from typing import Optional
import agent.api_client as api_client


GET_INVOICES_SCHEMA = {
    "type": "function",
    "name": "get_invoices",
    "description": "Retrieve invoices. Use this to check payment statuses, find overdue invoices, or review invoice history.",
    "parameters": {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["pending", "paid", "overdue"],
                "description": "Filter invoices by payment status.",
            },
            "overdue": {
                "type": "boolean",
                "description": "Filter to show only overdue invoices.",
            },
            "min_amount": {
                "type": "number",
                "description": "Minimum invoice amount to filter by.",
            },
            "max_amount": {
                "type": "number",
                "description": "Maximum invoice amount to filter by.",
            },
        },
        "required": [],
    },
}


GET_INVOICE_SCHEMA = {
    "type": "function",
    "name": "get_invoice",
    "description": "Retrieve a single invoice by its ID.",
    "parameters": {
        "type": "object",
        "properties": {
            "invoice_id": {
                "type": "integer",
                "description": "The unique identifier of the invoice to retrieve.",
            },
        },
        "required": ["invoice_id"],
    },
}


def get_invoices(
    status: Optional[str] = None,
    overdue: Optional[bool] = None,
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
) -> str:
    """Fetch invoices from the procurement API, optionally filtered."""
    params = {
        "status": status,
        "overdue": overdue,
        "min_amount": min_amount,
        "max_amount": max_amount,
    }
    return api_client.get("/invoices", params=params)


def get_invoice(invoice_id: int) -> str:
    """Fetch a single invoice by ID from the procurement API."""
    return api_client.get(f"/invoices/{invoice_id}")
