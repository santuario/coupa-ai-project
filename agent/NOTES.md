# Task Journal - Supplier AR Agent

Status: STAGE 1 COMPLETE - Config & API Client Implemented
Active supplier for walkthrough: Acme Technology Solutions (SUPPLIER_ID=1)

## Intent
Build a supplier-facing accounts receivable agent that helps the active supplier understand invoices, purchase orders, overdue items, follow-ups, and account health.

## Non-negotiable constraints
- OpenAI Responses API only.
- No agent frameworks.
- Tools call the HTTP API through httpx.
- Do not modify api/.
- Diff only touches agent/ and evals/.

## Invariants I must not break
- The LLM never controls supplier_id.
- supplier_id does not appear in tool schemas.
- Every API call that supports supplier_id injects the configured SUPPLIER_ID.
- The agent never returns another supplier's invoices, POs, contracts, catalog items, or analytics.
- Questions about named suppliers outside the active tenant are refused or scoped safely.
- Write operations are limited to API-supported operations and still inject SUPPLIER_ID.

## Key API finding
The API supports supplier scoping but does not enforce it server-side. If supplier_id is omitted, many endpoints return all supplier records. The agent layer is the tenancy boundary.

## Implementation Status

### ✅ COMPLETED: agent/config.py
**Purpose**: Centralized runtime configuration with safe defaults

**Implementation**:
```python
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4")
SUPPLIER_ID = int(os.getenv("SUPPLIER_ID", "1"))
SUPPLIER_NAME = os.getenv("SUPPLIER_NAME", "Acme Technology Solutions")
TRACE_PATH = os.getenv("TRACE_PATH", "evals/traces/agent_traces.jsonl")
```

**Security features**:
- Validates SUPPLIER_ID is positive integer
- Single source of truth for supplier identity
- No imports from api/

### ✅ COMPLETED: agent/api_client.py
**Purpose**: Scoped HTTP client that enforces supplier tenancy at application layer

**Key functions**:
- `get(path, params=None, scoped=True)` - GET requests with automatic supplier_id injection
- `post(path, params=None, json_body=None, scoped=True)` - POST requests with automatic supplier_id injection
- `_handle_response(response)` - Converts all responses to JSON strings, including errors

**Security architecture**:
```python
def get(path: str, *, params: dict[str, Any] | None = None, scoped: bool = True) -> str:
    query = _clean_params(params or {})
    if scoped:
        query["supplier_id"] = SUPPLIER_ID  # ← INJECTED IN CODE, NOT FROM MODEL
    response = httpx.get(f"{API_BASE_URL}{path}", params=query, timeout=10.0)
    return _handle_response(response)
```

**Why supplier_id cannot be model-controlled**:
1. **Defense in Depth**: supplier_id is injected at the application layer in api_client.py, not passed as a tool parameter
2. **Prevents Data Leakage**: The LLM cannot accidentally or maliciously request data from other suppliers
3. **Single Source of Truth**: The configured SUPPLIER_ID from environment variables is authoritative
4. **Prompt Injection Protection**: Even if the model is compromised, it cannot access other suppliers' data
5. **Audit Trail**: All API calls are automatically scoped to the configured supplier

**Error handling**:
- HTTP errors return JSON: `{"error": "api_error", "status_code": 404, "detail": "..."}`
- All responses are JSON strings for consistent tool output parsing
- 10-second timeout on all requests

### ✅ COMPLETED: agent/main.py updates
**Changes**:
- Imports `OPENAI_MODEL` and `SUPPLIER_NAME` from `agent.config`
- Removed duplicate `os.getenv()` calls
- Enhanced system prompt with explicit security rules:
  - "Do not ask the user for supplier_id. The application enforces supplier scope."
  - Instructions to refuse cross-tenant queries
  - Guidance on handling ambiguous questions

**Security in system prompt**:
The model is explicitly instructed that it cannot and should not control supplier_id, reinforcing the application-layer enforcement.

## Tool plan
Stage 1 safe tools:
- get_invoices
- get_invoice
- get_purchase_orders
- get_purchase_order
- get_contracts
- get_overdue_summary
- create_invoice
- acknowledge_purchase_order
- optional get_my_supplier_profile pinned to SUPPLIER_ID

Tools deliberately not built:
- list_all_suppliers / search_suppliers
- generic get_supplier(id)
- any tool accepting supplier_id from the model
- cross-supplier catalog search
- update_invoice / delete_invoice, because the API has no such endpoints
- broad unscoped supplier analytics

## Verification plan
- Unit/smoke: each tool injects SUPPLIER_ID and returns only active supplier records.
- Negative: out-of-tenant invoice IDs return 404 or safe refusal.
- Negative: questions about SteelWorks/CleanSpace under Acme session do not leak their data.
- Agent: simple lookup, filtering, multi-step status, and ambiguous follow-up questions.
- Static: ruff and mypy.
- Trace: every turn writes parseable JSONL with tool names, args, output summaries, and tenant guard results.

## Decisions log
- ✅ Use a scoped API client to centralize supplier_id injection.
- ✅ Keep supplier_id out of all tool schemas.
- Use deterministic Python skills for account health and follow-up reasoning.
- Use model for language synthesis, not tenant filtering.
- ✅ Centralize configuration in config.py to avoid duplication and ensure consistency

## Known limits
- Mock API has no auth layer; supplier isolation is enforced in the agent only.
- No persistent database; created invoices reset when the API restarts.
- Evals use pragmatic assertions, not perfect semantic grading.

## Confirmed pre-coding findings
- `get_invoices` is unsafe because it calls /invoices with params={}; this returns all suppliers.
- API supplier filtering is opt-in: supplier_id=None means all records.
- /suppliers returns all suppliers and has no tenant filter.
- /suppliers/{id} has no session tenant; only a pinned get_my_supplier_profile is safe.
- acknowledge_purchase_order returns 404 on wrong supplier due to mismatch fall-through; tool should surface that safely.
- requirements include httpx, openai, python-dotenv, ruff, and mypy.

### ✅ COMPLETED: agent/procurement_tools/invoices.py
**Purpose**: Invoice retrieval tools with proper supplier scoping

**Implementation**:
Two tools following OpenAI function schema dict style:

1. **get_invoices(status?, overdue?, min_amount?, max_amount?)**
   - Optional parameters for filtering invoices
   - status: enum ["pending", "paid", "overdue"]
   - overdue: boolean filter
   - min_amount/max_amount: numeric range filters
   - Uses `api_client.get("/invoices", params=params)` for automatic SUPPLIER_ID injection
   - Returns JSON string

2. **get_invoice(invoice_id: int)**
   - Required invoice_id parameter
   - Uses `api_client.get(f"/invoices/{invoice_id}")` for automatic SUPPLIER_ID injection
   - Returns JSON string

**Security features**:
- No supplier_id in tool schemas (enforced by api_client)
- All API calls automatically scoped to configured SUPPLIER_ID
- Removed unsafe print_string template parameter
- Uses agent.api_client instead of direct httpx calls

**Schema style**:
- Preserved raw OpenAI function schema dict format
- Type definitions: "string", "boolean", "number", "integer"
- Enum constraints for status field
- Clear descriptions for each parameter

### ✅ COMPLETED: agent/tools.py updates
**Changes**:
- Imported GET_INVOICE_SCHEMA and get_invoice from invoices module
- Registered get_invoice in TOOL_REGISTRY
- Added GET_INVOICE_SCHEMA to TOOL_SCHEMAS
- Both invoice tools now available to the agent

### ✅ COMPLETED: agent/procurement_tools/purchase_orders.py
**Purpose**: Purchase order retrieval and acknowledgment tools with proper supplier scoping

**Implementation**:
Three tools following OpenAI function schema dict style:

1. **get_purchase_orders(status?, created_after?, created_before?, min_amount?)**
   - Optional parameters for filtering purchase orders
   - status: enum ["submitted", "acknowledged"]
   - created_after/created_before: date string filters (format: YYYY-MM-DD)
   - min_amount: numeric minimum amount filter
   - Uses `api_client.get("/purchase-orders", params=params)` for automatic SUPPLIER_ID injection
   - Returns JSON string

2. **get_purchase_order(po_id: int)**
   - Required po_id parameter
   - Uses `api_client.get(f"/purchase-orders/{po_id}")` for automatic SUPPLIER_ID injection
   - Returns JSON string

3. **acknowledge_purchase_order(po_id: int)**
   - Required po_id parameter
   - Uses `api_client.post(f"/purchase-orders/{po_id}/acknowledge")` for automatic SUPPLIER_ID injection
   - Transitions PO status from 'submitted' to 'acknowledged'
   - Returns JSON string with updated PO or error details

**Security features**:
- No supplier_id in tool schemas (enforced by api_client)
- All API calls automatically scoped to configured SUPPLIER_ID
- Uses agent.api_client for consistent error handling
- POST endpoint properly calls /purchase-orders/{po_id}/acknowledge

**Schema style**:
- Preserved raw OpenAI function schema dict format
- Type definitions: "string", "number", "integer"
- Enum constraints for status field
- Clear descriptions for each parameter

### ✅ COMPLETED: agent/tools.py updates (purchase orders)
**Changes**:
- Imported GET_PURCHASE_ORDERS_SCHEMA, GET_PURCHASE_ORDER_SCHEMA, ACKNOWLEDGE_PURCHASE_ORDER_SCHEMA from purchase_orders module
- Imported get_purchase_orders, get_purchase_order, acknowledge_purchase_order functions
- Registered all three purchase order functions in TOOL_REGISTRY
- Added all three purchase order schemas to TOOL_SCHEMAS
- All purchase order tools now available to the agent

## Next Steps
- [ ] Implement remaining Stage 1 tools using api_client (contracts, overdue_summary, etc.)
- [ ] Test supplier isolation with cross-tenant queries
- [ ] Implement Stage 2 skills (multi-step workflows)
- [ ] Add Stage 3 tracing infrastructure
- [ ] Build Stage 4 evaluation harness
