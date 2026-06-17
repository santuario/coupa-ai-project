"""Deterministic helper functions for high-level AR capabilities.

These skills call safe tool implementations or the scoped API client,
parse JSON, and return JSON strings. They provide deterministic business
logic that the agent can use for complex queries.

Rules:
- No supplier_id argument (always uses scoped client)
- Use scoped client or safe tool functions
- Keep facts deterministic
- Return JSON strings
"""

from __future__ import annotations

import json
from typing import Any

import agent.api_client as api_client


def get_ar_status() -> str:
    """Get comprehensive accounts receivable status for the active supplier.
    
    Returns a JSON string containing:
    - invoices_by_status: breakdown of invoice counts and amounts by status
    - overdue_summary: overdue invoice details with aging buckets
    - active_contracts: count of active contracts
    - pending_contracts: count of pending renewal contracts
    - submitted_pos: count of submitted (unacknowledged) purchase orders
    - recommended_followups: concise list of recommended actions
    
    This is a deterministic aggregation of multiple API calls.
    """
    result: dict[str, Any] = {
        "invoices_by_status": {},
        "overdue_summary": {},
        "active_contracts": 0,
        "pending_contracts": 0,
        "submitted_pos": 0,
        "recommended_followups": [],
    }
    
    # Fetch all invoices
    invoices_response = api_client.get("/invoices", params={})
    try:
        invoices_data = json.loads(invoices_response)
        if isinstance(invoices_data, dict) and "error" in invoices_data:
            return json.dumps({"error": "Failed to fetch invoices", "details": invoices_data})
        
        invoices = invoices_data if isinstance(invoices_data, list) else []
        
        # Group invoices by status
        status_breakdown: dict[str, list[Any]] = {"pending": [], "paid": [], "overdue": []}
        for inv in invoices:
            status = inv.get("status", "").lower()
            if status in status_breakdown:
                status_breakdown[status].append(inv)
        
        # Calculate summary by status
        for status, inv_list in status_breakdown.items():
            result["invoices_by_status"][status] = {
                "count": len(inv_list),
                "total_amount": sum(inv.get("amount", 0) for inv in inv_list),
            }
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        return json.dumps({"error": "Failed to parse invoices", "details": str(e)})
    
    # Fetch overdue summary
    overdue_response = api_client.get("/analytics/overdue-summary", params={})
    try:
        overdue_data = json.loads(overdue_response)
        if isinstance(overdue_data, dict) and "error" not in overdue_data:
            result["overdue_summary"] = overdue_data
    except (json.JSONDecodeError, KeyError, TypeError):
        result["overdue_summary"] = {"error": "Failed to parse overdue summary"}
    
    # Fetch contracts
    contracts_response = api_client.get("/contracts", params={})
    try:
        contracts_data = json.loads(contracts_response)
        if isinstance(contracts_data, list):
            result["active_contracts"] = sum(
                1 for c in contracts_data if c.get("status") == "active"
            )
            result["pending_contracts"] = sum(
                1 for c in contracts_data if c.get("status") == "pending_renewal"
            )
    except (json.JSONDecodeError, KeyError, TypeError):
        pass
    
    # Fetch submitted POs
    pos_response = api_client.get("/purchase-orders", params={"status": "submitted"})
    try:
        pos_data = json.loads(pos_response)
        if isinstance(pos_data, list):
            result["submitted_pos"] = len(pos_data)
    except (json.JSONDecodeError, KeyError, TypeError):
        pass
    
    # Generate recommended follow-ups
    followups = []
    
    overdue_count = result["invoices_by_status"].get("overdue", {}).get("count", 0)
    if overdue_count > 0:
        followups.append(f"Follow up on {overdue_count} overdue invoice(s)")
    
    if result["submitted_pos"] > 0:
        followups.append(f"Acknowledge {result['submitted_pos']} submitted purchase order(s)")
    
    if result["pending_contracts"] > 0:
        followups.append(f"Review {result['pending_contracts']} contract(s) pending renewal")
    
    pending_count = result["invoices_by_status"].get("pending", {}).get("count", 0)
    if pending_count > 0:
        followups.append(f"Monitor {pending_count} pending invoice(s) for payment")
    
    if not followups:
        followups.append("No urgent actions required - account is in good standing")
    
    result["recommended_followups"] = followups
    
    return json.dumps(result, indent=2)


def get_delivered_pos_without_paid_invoice() -> str:
    """Identify purchase orders with delivery dates but no corresponding paid invoice.
    
    Returns a JSON string containing a list of POs that have been delivered
    (delivery_date is present) but do not have a corresponding paid invoice.
    
    Each entry includes:
    - po_id: Purchase order ID
    - total_amount: PO amount
    - delivery_date: Date the PO was delivered
    - invoice_status: Status of associated invoice (if any)
    - invoice_id: ID of associated invoice (if any)
    
    This helps identify delivered goods/services that haven't been invoiced or paid.
    """
    result: dict[str, Any] = {
        "delivered_pos_without_paid_invoice": [],
        "summary": {
            "total_count": 0,
            "total_amount": 0.0,
        },
    }
    
    # Fetch all acknowledged POs (only acknowledged POs can have delivery dates)
    pos_response = api_client.get("/purchase-orders", params={"status": "acknowledged"})
    try:
        pos_data = json.loads(pos_response)
        if isinstance(pos_data, dict) and "error" in pos_data:
            return json.dumps({"error": "Failed to fetch purchase orders", "details": pos_data})
        
        pos_list = pos_data if isinstance(pos_data, list) else []
    except (json.JSONDecodeError, TypeError) as e:
        return json.dumps({"error": "Failed to parse purchase orders", "details": str(e)})
    
    # Fetch all invoices
    invoices_response = api_client.get("/invoices", params={})
    try:
        invoices_data = json.loads(invoices_response)
        if isinstance(invoices_data, dict) and "error" in invoices_data:
            return json.dumps({"error": "Failed to fetch invoices", "details": invoices_data})
        
        invoices_list = invoices_data if isinstance(invoices_data, list) else []
    except (json.JSONDecodeError, TypeError) as e:
        return json.dumps({"error": "Failed to parse invoices", "details": str(e)})
    
    # Build a map of po_id -> paid invoices
    paid_invoice_map: dict[int, dict] = {}
    all_invoice_map: dict[int, dict] = {}
    
    for inv in invoices_list:
        po_id = inv.get("po_id")
        if po_id is not None:
            all_invoice_map[po_id] = inv
            if inv.get("status") == "paid":
                paid_invoice_map[po_id] = inv
    
    # Identify POs with delivery_date but no paid invoice
    for po in pos_list:
        delivery_date = po.get("delivery_date")
        po_id = po.get("id")
        
        # Skip POs without delivery dates
        if not delivery_date:
            continue
        
        # Check if there's a paid invoice for this PO
        if po_id in paid_invoice_map:
            continue
        
        # This PO has been delivered but has no paid invoice
        entry: dict[str, Any] = {
            "po_id": po_id,
            "total_amount": po.get("total_amount", 0.0),
            "currency": po.get("currency", "USD"),
            "delivery_date": delivery_date,
            "invoice_status": None,
            "invoice_id": None,
        }
        
        # Check if there's any invoice (paid or not) for this PO
        if po_id in all_invoice_map:
            invoice = all_invoice_map[po_id]
            entry["invoice_status"] = invoice.get("status")
            entry["invoice_id"] = invoice.get("id")
        
        result["delivered_pos_without_paid_invoice"].append(entry)
        result["summary"]["total_count"] += 1
        result["summary"]["total_amount"] += entry["total_amount"]
    
    return json.dumps(result, indent=2)
