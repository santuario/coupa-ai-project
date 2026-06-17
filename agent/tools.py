"""Tool registry and execution engine."""

import json
from typing import Callable

from agent.procurement_tools.invoices import (
    GET_INVOICES_SCHEMA,
    GET_INVOICE_SCHEMA,
    get_invoices,
    get_invoice,
)
from agent.procurement_tools.purchase_orders import (
    GET_PURCHASE_ORDERS_SCHEMA,
    GET_PURCHASE_ORDER_SCHEMA,
    ACKNOWLEDGE_PURCHASE_ORDER_SCHEMA,
    get_purchase_orders,
    get_purchase_order,
    acknowledge_purchase_order,
)

TOOL_REGISTRY: dict[str, Callable[..., str]] = {
    "get_invoices": get_invoices,
    "get_invoice": get_invoice,
    "get_purchase_orders": get_purchase_orders,
    "get_purchase_order": get_purchase_order,
    "acknowledge_purchase_order": acknowledge_purchase_order,
}

TOOL_SCHEMAS: list[dict] = [
    GET_INVOICES_SCHEMA,
    GET_INVOICE_SCHEMA,
    GET_PURCHASE_ORDERS_SCHEMA,
    GET_PURCHASE_ORDER_SCHEMA,
    ACKNOWLEDGE_PURCHASE_ORDER_SCHEMA,
]



def execute_tool_call(tool_call, registry: dict[str, Callable[..., str]] = TOOL_REGISTRY) -> str:
    """Execute a tool call and return the result as a string."""
    name = tool_call.name
    args = json.loads(tool_call.arguments) if tool_call.arguments else {}

    print(f"  -> calling {name}({args})")

    result = registry[name](**args)
    return result if isinstance(result, str) else json.dumps(result)
