"""Analytics tools.

Available API endpoints:
  GET  /analytics/overdue-summary    — Summary of overdue invoices with aging buckets (params: supplier_id)
  GET  /analytics/spend-by-supplier  — Total invoiced amount per supplier (params: supplier_id)
  
Note: spend-by-supplier is NOT exposed as a tool to prevent unscoped broad analytics.
Only scoped analytics like overdue-summary are available.
"""

import agent.api_client as api_client


GET_OVERDUE_SUMMARY_SCHEMA = {
    "type": "function",
    "name": "get_overdue_summary",
    "description": "Get a summary of overdue invoices with aging buckets (1-30 days, 31-60 days, 61-90 days, 90+ days). Use this to understand overdue payment status and aging.",
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


def get_overdue_summary() -> str:
    """Fetch overdue invoice summary from the procurement API with aging buckets."""
    return api_client.get("/analytics/overdue-summary")
