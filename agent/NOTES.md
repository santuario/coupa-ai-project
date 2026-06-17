# Task Journal - Supplier AR Agent

Status: ✅ STAGE 1 COMPLETE - All Tools Implemented & Registered
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
**Purpose**: Invoice retrieval and creation tools with proper supplier scoping

**Implementation**:
Three tools following OpenAI function schema dict style:

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

3. **create_invoice(amount: float, due_date: str, po_id?: int, currency?: str)**
   - Required parameters: amount (number), due_date (string in YYYY-MM-DD format)
   - Optional parameters: po_id (integer), currency (string, defaults to "USD")
   - Uses `api_client.post("/invoices", json_body=json_body)` for automatic SUPPLIER_ID injection
   - Schema-level validation ensures amount and due_date are required
   - Returns JSON string with created invoice or error details

**Security features**:
- No supplier_id in tool schemas (enforced by api_client)
- All API calls automatically scoped to configured SUPPLIER_ID
- Removed unsafe print_string template parameter
- Uses agent.api_client instead of direct httpx calls
- POST endpoint properly injects SUPPLIER_ID through scoped api_client

**Schema style**:
- Preserved raw OpenAI function schema dict format
- Type definitions: "string", "boolean", "number", "integer"
- Enum constraints for status field
- Clear descriptions for each parameter
- Required fields enforced at schema level

**Design decisions**:
- No update_invoice or delete_invoice tools (API has no such endpoints)
- create_invoice follows same scoped pattern as acknowledge_purchase_order

### ✅ COMPLETED: agent/tools.py updates (invoices)
**Changes**:
- Imported GET_INVOICE_SCHEMA, CREATE_INVOICE_SCHEMA and get_invoice, create_invoice from invoices module
- Registered get_invoice and create_invoice in TOOL_REGISTRY
- Added GET_INVOICE_SCHEMA and CREATE_INVOICE_SCHEMA to TOOL_SCHEMAS
- All three invoice tools now available to the agent

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

### ✅ COMPLETED: agent/procurement_tools/contracts.py
**Purpose**: Contract retrieval tools with proper supplier scoping

**Implementation**:
One tool following OpenAI function schema dict style:

1. **get_contracts(status?, expiring_within_days?)**
   - Optional parameters for filtering contracts
   - status: enum ["active", "expired", "pending_renewal"]
   - expiring_within_days: integer filter for contracts expiring within N days
   - Uses `api_client.get("/contracts", params=params)` for automatic SUPPLIER_ID injection
   - Returns JSON string

**Security features**:
- No supplier_id in tool schema (enforced by api_client)
- All API calls automatically scoped to configured SUPPLIER_ID
- Uses agent.api_client for consistent error handling

**Schema style**:
- Preserved raw OpenAI function schema dict format
- Type definitions: "string", "integer"
- Enum constraints for status field
- Clear descriptions for each parameter

### ✅ COMPLETED: agent/procurement_tools/analytics.py
**Purpose**: Analytics tools with proper supplier scoping - deliberately limited to prevent unscoped broad analytics

**Implementation**:
One tool following OpenAI function schema dict style:

1. **get_overdue_summary()**
   - No parameters - automatically scoped to configured SUPPLIER_ID
   - Returns overdue invoice summary with aging buckets (1-30, 31-60, 61-90, 90+ days)
   - Uses `api_client.get("/analytics/overdue-summary")` for automatic SUPPLIER_ID injection
   - Returns JSON string with total_overdue_amount, total_overdue_count, and aging_buckets

**Security features**:
- No supplier_id in tool schema (enforced by api_client)
- All API calls automatically scoped to configured SUPPLIER_ID
- Deliberately excludes spend-by-supplier endpoint to prevent unscoped broad analytics
- Only scoped analytics exposed to the agent

**Design decision**:
- spend-by-supplier endpoint exists in API but is NOT exposed as a tool
- This prevents the agent from accessing unscoped cross-supplier analytics
- Keeps analytics focused on the active supplier's data only

### ✅ COMPLETED: agent/tools.py updates (contracts and analytics)
**Changes**:
- Imported GET_CONTRACTS_SCHEMA and get_contracts from contracts module
- Imported GET_OVERDUE_SUMMARY_SCHEMA and get_overdue_summary from analytics module
- Registered get_contracts in TOOL_REGISTRY
- Registered get_overdue_summary in TOOL_REGISTRY
- Added GET_CONTRACTS_SCHEMA to TOOL_SCHEMAS
- Added GET_OVERDUE_SUMMARY_SCHEMA to TOOL_SCHEMAS
- Agent now has 8 total tools available: 3 invoice tools, 3 purchase order tools, 1 contract tool, 1 analytics tool

## Stage 1 Summary - Tools Implementation Complete

### ✅ Tools Successfully Added (8 total)
**Invoice Tools (3):**
1. `get_invoices` - List/filter invoices with optional status, overdue, min/max amount filters
2. `get_invoice` - Retrieve single invoice by ID
3. `create_invoice` - Create new invoice with amount, due_date (required), po_id, currency (optional, defaults to USD)

**Purchase Order Tools (3):**
4. `get_purchase_orders` - List/filter POs with optional status, date range, min amount filters
5. `get_purchase_order` - Retrieve single PO by ID
6. `acknowledge_purchase_order` - Acknowledge submitted PO (transitions status to 'acknowledged')

**Contract Tools (1):**
7. `get_contracts` - List/filter contracts with optional status and expiring_within_days filters

**Analytics Tools (1):**
8. `get_overdue_summary` - Get overdue invoice summary with aging buckets (no parameters)

### 🔒 How supplier_id is Injected
**Application-layer enforcement in api_client.py:**
```python
def get(path: str, *, params: dict[str, Any] | None = None, scoped: bool = True) -> str:
    query = _clean_params(params or {})
    if scoped:
        query["supplier_id"] = SUPPLIER_ID  # ← INJECTED HERE, NOT FROM MODEL
    response = httpx.get(f"{API_BASE_URL}{path}", params=query, timeout=10.0)
    return _handle_response(response)

def post(path: str, *, params: dict[str, Any] | None = None, json_body: dict[str, Any] | None = None, scoped: bool = True) -> str:
    query = _clean_params(params or {})
    if scoped:
        query["supplier_id"] = SUPPLIER_ID  # ← INJECTED HERE, NOT FROM MODEL
    response = httpx.post(f"{API_BASE_URL}{path}", params=query, json=_clean_params(json_body or {}), timeout=10.0)
    return _handle_response(response)
```

**Key security properties:**
- supplier_id NEVER appears in tool schemas
- LLM cannot control or see supplier_id
- All tools use scoped=True by default
- SUPPLIER_ID comes from environment config, not model input
- Defense in depth: even if model is compromised, it cannot access other suppliers' data

### ❌ Tools Deliberately NOT Built
**Security reasons:**
- `list_all_suppliers` / `search_suppliers` - Would expose cross-tenant data
- `get_supplier(id)` - Would allow model to query arbitrary suppliers
- Any tool accepting supplier_id as a parameter - Violates tenancy boundary
- `/analytics/spend-by-supplier` endpoint - Unscoped cross-supplier analytics

**API limitations:**
- `update_invoice` - API has no PATCH/PUT /invoices endpoint
- `delete_invoice` - API has no DELETE /invoices endpoint
- `update_purchase_order` - Not supported by API
- `delete_purchase_order` - Not supported by API

**Design decisions:**
- `get_my_supplier_profile` - Deferred (not critical for Stage 1)
- Cross-supplier catalog search - Out of scope for supplier AR agent
- Broad unscoped analytics - Deliberately excluded for security

### 🧪 Manual Prompts Tested
**Successful test cases:**
1. ✅ "Create an invoice for PO 1002 for 13600 USD due 2025-06-20"
   - Initially failed: create_invoice was not registered in tools.py
   - Fixed: Added CREATE_INVOICE_SCHEMA and create_invoice to TOOL_REGISTRY and TOOL_SCHEMAS
   - Now works: Agent can successfully create invoices

**Expected behavior:**
- Agent should call `create_invoice(amount=13600, due_date="2025-06-20", po_id=1002, currency="USD")`
- API automatically scopes to SUPPLIER_ID=1 via api_client.post
- Returns created invoice JSON or error details

### 🔧 Bugs Fixed During Stage 1
**Issue:** create_invoice function existed but was not registered
- **Root cause:** invoices.py had the function and schema, but tools.py was never updated
- **Fix:** Added imports and registration in tools.py (lines 6-12, 33, 43)
- **Impact:** Agent now has access to all 8 planned tools

### 📋 Known Gaps Before Stage 2
**Testing:**
- [ ] No automated unit tests for tool functions yet
- [ ] No cross-tenant isolation tests (e.g., try to access SteelWorks data from Acme session)
- [ ] No negative tests for out-of-tenant invoice IDs
- [ ] No static analysis (ruff/mypy) run yet

**Functionality:**
- [ ] No multi-step workflows (e.g., "acknowledge all submitted POs")
- [ ] No deterministic Python skills for account health reasoning
- [ ] No follow-up question handling
- [ ] No tracing infrastructure (JSONL logging)

**Error handling:**
- [ ] Tool errors return JSON but agent may not handle them gracefully
- [ ] No retry logic for transient API failures
- [ ] No validation of date formats before API calls

**Documentation:**
- [ ] No inline examples in tool descriptions
- [ ] No user-facing documentation for supported queries
- [ ] No runbook for common agent tasks

### 🎯 Stage 1 Success Criteria - MET
✅ All 8 planned tools implemented with proper supplier scoping
✅ No supplier_id in any tool schema
✅ api_client.py enforces tenancy at application layer
✅ Tools registered in TOOL_REGISTRY and TOOL_SCHEMAS
✅ Manual prompt testing confirms create_invoice works
✅ Security invariants maintained (LLM never controls supplier_id)
✅ Only API-supported write operations exposed (create_invoice, acknowledge_purchase_order)

## Stage 2 - Deterministic Skills Implementation

### ✅ COMPLETED: agent/skills.py
**Purpose**: High-level deterministic helper functions for complex AR queries

**Implementation**:
Two skills that aggregate multiple API calls and provide deterministic business logic:

1. **get_ar_status()**
   - Aggregates data from multiple endpoints: /invoices, /analytics/overdue-summary, /contracts, /purchase-orders
   - Returns comprehensive AR status including:
     - invoices_by_status: breakdown of counts and amounts by status (pending, paid, overdue)
     - overdue_summary: aging buckets from analytics API
     - active_contracts: count of active contracts
     - pending_contracts: count of contracts pending renewal
     - submitted_pos: count of unacknowledged POs
     - recommended_followups: deterministic list of recommended actions
   - Deterministic logic: no LLM reasoning, pure data aggregation
   - Error handling: gracefully handles API failures, returns JSON error objects

2. **get_delivered_pos_without_paid_invoice()**
   - Identifies POs with delivery_date but no corresponding paid invoice
   - Cross-references acknowledged POs with all invoices
   - Returns PO details with invoice status context
   - Helps identify delivered goods/services that haven't been invoiced or paid
   - Includes summary with total count and amount

**Security features**:
- No supplier_id arguments - uses scoped api_client exclusively
- All API calls automatically scoped to configured SUPPLIER_ID
- Returns JSON strings for consistent tool integration
- Type-safe with mypy annotations

### ✅ COMPLETED: Updated SYSTEM_PROMPT in agent/main.py
**Changes**:
Added tool selection guidance to prefer high-level skills for ambiguous queries:

```
Tool selection guidance:
- For exact invoice or PO lookups (e.g., "show me invoice 1001"), use get_invoice or get_purchase_order.
- For account health questions (e.g., "how is my account?", "what's my AR status?"), use get_ar_status.
- For follow-up questions (e.g., "what should I follow up on?", "what needs attention?"), use get_ar_status.
- For delivered POs without payment (e.g., "which delivered orders haven't been paid?"), use get_delivered_pos_without_paid_invoice.
- For cross-supplier named questions (e.g., "show me SteelWorks invoices"), refuse politely and scope to the active supplier only.
```

Also added:
- "Do not reveal internal supplier_id values unless needed for debugging."

### 🎯 Stage 2 Design Decisions

#### Which logic lives in skills instead of the model?
**Skills (deterministic Python):**
- Multi-endpoint data aggregation (get_ar_status fetches from 4 endpoints)
- Business logic for recommended follow-ups (deterministic rules based on counts)
- Cross-referencing data (matching POs with invoices by po_id)
- Filtering and grouping (invoices by status, POs with delivery dates)
- Summary calculations (totals, counts, amounts)

**Model (LLM reasoning):**
- Natural language understanding of user intent
- Deciding which tool/skill to call based on the query
- Synthesizing tool outputs into conversational responses
- Handling ambiguous or multi-step questions
- Explaining results in user-friendly language

**Rationale**: Deterministic logic in Python is faster, more reliable, and easier to test than LLM reasoning. The model focuses on language understanding and synthesis, not data processing.

#### How get_ar_status avoids broad analytics leakage
**Security measures**:
1. **Scoped API calls**: All endpoints called with scoped=True, injecting SUPPLIER_ID
2. **No cross-supplier aggregation**: Only fetches data for the active supplier
3. **Deliberate endpoint selection**: Uses /analytics/overdue-summary (scoped) instead of /analytics/spend-by-supplier (unscoped)
4. **No supplier_id parameter**: Function signature has no supplier_id argument, preventing model control
5. **Deterministic filtering**: All grouping/filtering happens in Python after scoped API calls

**What it does NOT expose**:
- Cross-supplier analytics or comparisons
- Unscoped spend-by-supplier data
- Other suppliers' invoice/PO/contract data
- Supplier_id values (unless debugging)

#### Which ambiguous questions it supports
**Supported queries for get_ar_status**:
- "How is my account?" → Full AR status with all metrics
- "What should I follow up on?" → Recommended actions based on data
- "What needs attention?" → Prioritized follow-ups
- "Give me an overview of my AR" → Comprehensive status report
- "What's my account health?" → Status with recommendations
- "Any urgent items?" → Overdue invoices, submitted POs, pending renewals

**Supported queries for get_delivered_pos_without_paid_invoice**:
- "Which delivered orders haven't been paid?" → POs with delivery_date but no paid invoice
- "Show me delivered POs without invoices" → Same as above
- "What deliveries are awaiting payment?" → Same as above
- "Find POs that were delivered but not invoiced" → Same as above

**NOT supported (requires exact lookups)**:
- "Show me invoice 1001" → Use get_invoice instead
- "What's the status of PO 2003?" → Use get_purchase_order instead
- "List all pending invoices" → Use get_invoices with status filter instead

#### Remaining limits
**Functionality gaps**:
- [ ] Skills are not yet registered as tools (can be called by model if registered)
- [ ] No multi-step workflows (e.g., "acknowledge all submitted POs and create invoices")
- [ ] No date-based filtering in skills (e.g., "overdue invoices from last month")
- [ ] No currency conversion or multi-currency aggregation
- [ ] No trend analysis or historical comparisons

**Testing gaps**:
- [ ] No unit tests for skills functions
- [ ] No integration tests with mock API
- [ ] No cross-tenant isolation tests for skills
- [ ] No performance tests for multi-endpoint aggregation

**Error handling gaps**:
- [ ] No retry logic for transient API failures
- [ ] No partial success handling (e.g., if one endpoint fails, return partial data)
- [ ] No timeout configuration for slow API calls
- [ ] No circuit breaker for repeated failures

**Documentation gaps**:
- [ ] No inline examples in skill docstrings
- [ ] No user-facing documentation for supported queries
- [ ] No runbook for common skill usage patterns

### 🎯 Stage 2 Success Criteria - MET
✅ Created agent/skills.py with two deterministic helper functions
✅ get_ar_status aggregates data from 4 endpoints with deterministic follow-up logic
✅ get_delivered_pos_without_paid_invoice cross-references POs and invoices
✅ Updated SYSTEM_PROMPT with tool selection guidance
✅ No supplier_id arguments in skills (uses scoped client)
✅ Returns JSON strings for consistent tool integration
✅ Passes mypy type checking and Python syntax validation
✅ Security invariants maintained (all API calls scoped to SUPPLIER_ID)

## Stage 3 - Tracing Infrastructure Implementation

### ✅ COMPLETED: agent/tracing.py
**Purpose**: Lightweight JSONL trace writing for agent conversation turns with tenant guard security checks

**Implementation**:
Core tracing module with three main functions:

1. **write_trace(trace_path, model, active_supplier_name, user_message, tool_calls, final_answer, elapsed_ms, active_supplier_id)**
   - Writes one JSON object per conversation turn to JSONL file
   - Automatically creates trace directory if it doesn't exist
   - Includes comprehensive turn data:
     - timestamp (UTC ISO format)
     - model name
     - active_supplier_name
     - user_message
     - tool_calls (list with name, arguments, output_summary, status)
     - tenant_guard (security check results)
     - final_answer
     - elapsed_ms
   - Runs tenant guard checks on all tool calls
   - Summarizes outputs to avoid storing full sensitive data

2. **check_tenant_guard(tool_calls, active_supplier_id)**
   - Analyzes tool calls for tenant isolation violations
   - Enforces three strict rules:
     - **RULE 1**: supplier_id must NOT be in arguments (application enforces scope)
     - **RULE 2**: All output records must have supplier_id == active_supplier_id
     - **RULE 3**: Parsing failures recorded as "UNKNOWN", not pass
   - Returns TenantGuardTrace with:
     - supplier_id_in_args: bool
     - cross_tenant_records_seen: bool
     - notes: list[str] with detailed violation messages
   - Reports ALL violations, not just first one
   - Distinguishes between VIOLATION (security issue) and UNKNOWN (parsing issue)

3. **read_traces(trace_path)**
   - Reads all traces from JSONL file
   - Returns list of ConversationTurnTrace objects
   - Handles missing files gracefully

**Helper functions**:
- **summarize_output(output, max_length=200)**: Creates summaries of tool outputs
  - Lists: "[List with N items]"
  - Dicts: "{Dict with keys: key1, key2, ...}"
  - Long strings: Truncated with "..."
  - Avoids storing full sensitive raw data

- **ensure_trace_directory(trace_path)**: Automatic directory creation with parents=True

**Security features**:
- No full sensitive outputs stored - only summaries
- Tenant guard checks run automatically on every turn
- Detects supplier_id in arguments (violation)
- Validates all output records match active supplier_id
- Flags unparseable outputs as UNKNOWN
- Does not block execution - only records findings

**TypedDict schemas**:
- ToolCallTrace: name, arguments, output_summary, status
- TenantGuardTrace: supplier_id_in_args, cross_tenant_records_seen, notes
- ConversationTurnTrace: Complete turn data structure

### ✅ COMPLETED: agent/main.py tracing integration
**Changes**:
- Imported write_trace from agent.tracing
- Imported SUPPLIER_ID and TRACE_PATH from agent.config
- Added timing tracking: turn_start_time and elapsed_ms calculation
- Added tool call collection: turn_tool_calls list tracks all tool calls in a turn
- Added trace writing after each turn completes
- Added graceful error handling for trace writing failures
- Preserved raw Responses API loop (no framework, no Chat Completions)
- Added context window hygiene:
  - Keeps developer prompt separate
  - Maintains last 20 conversation turns (40 messages)
  - Automatically prunes oldest messages when limit exceeded
  - Formula: MAX_HISTORY_TURNS * 2 + 1 (for developer prompt)

**Integration flow**:
1. User enters message
2. Timer starts (turn_start_time)
3. Tool execution loop runs (original behavior preserved)
4. Each tool call tracked with name, arguments, output, status
5. Final answer displayed to user
6. Elapsed time calculated in milliseconds
7. write_trace() called with all turn data
8. Tenant guard checks run automatically
9. Trace written to JSONL file
10. Old conversation history pruned if needed
11. Loop continues

**Error handling**:
- Trace writing wrapped in try/except
- Failures print warning but don't crash agent
- Terminal output remains clean and readable

### ✅ COMPLETED: agent/test_tracing.py
**Purpose**: Comprehensive test suite for tracing module

**Test coverage**:
1. **test_summarize_output()**: Tests output summarization
   - JSON lists → "[List with N items]"
   - JSON dicts → "{Dict with keys: ...}"
   - Long strings → Truncated with "..."

2. **test_tenant_guard()**: Tests tenant guard with new rules (6 scenarios)
   - supplier_id in arguments → VIOLATION (even if correct)
   - No supplier_id in arguments, correct output → PASS
   - Cross-tenant data in output → VIOLATION
   - Multiple violations in list → Reports all violations
   - Parsing failure → UNKNOWN
   - Empty output → PASS

3. **test_write_and_read_trace()**: Tests JSONL writing and reading
   - Writes trace to temporary directory
   - Verifies file creation
   - Reads trace back and validates all fields
   - Tests multiple traces in same file

4. **test_directory_creation()**: Tests automatic directory creation
   - Uses deeply nested path that doesn't exist
   - Verifies directories created automatically

**Test results**: ✅ All tests pass

### 🔒 Tenant Guard Security Rules

**RULE 1: supplier_id must NOT be in arguments**
- Rationale: Application enforces scope via api_client.py, not tool parameters
- Violation: Any tool call with supplier_id in arguments
- Detection: Checks all tool call arguments for "supplier_id" key
- Message: "VIOLATION: Tool 'X' has supplier_id in arguments. Application should enforce scope, not pass supplier_id explicitly."

**RULE 2: All output records must match active supplier_id**
- Rationale: Prevents cross-tenant data leakage in API responses
- Violation: Any record with supplier_id != active_supplier_id
- Detection: Parses JSON outputs (dicts and lists), checks all supplier_id fields
- Message: "VIOLATION: Tool 'X' returned record with supplier_id=Y, expected Z"
- Reports ALL violations, not just first one

**RULE 3: Parsing failures recorded as UNKNOWN**
- Rationale: Unparseable outputs cannot be verified for tenant isolation
- Status: UNKNOWN (not pass, not violation)
- Detection: JSON parsing exceptions (JSONDecodeError, TypeError)
- Message: "UNKNOWN: Tool 'X' output could not be parsed as JSON. Cannot verify tenant isolation. Error: JSONDecodeError"

**Non-blocking design**:
- Tenant guard does NOT block execution
- Only records findings in traces
- Allows post-hoc security analysis
- Enables evaluation of tenant isolation effectiveness

### 📊 Trace Format (JSONL)

Each line in the trace file is a JSON object with this structure:
```json
{
  "timestamp": "2026-06-17T07:24:00.123456+00:00",
  "model": "gpt-5.4",
  "active_supplier_name": "Acme Technology Solutions",
  "user_message": "Show me pending invoices",
  "tool_calls": [
    {
      "name": "get_invoices",
      "arguments": {"status": "pending"},
      "output_summary": "[List with 3 items]",
      "status": "success"
    }
  ],
  "tenant_guard": {
    "supplier_id_in_args": false,
    "cross_tenant_records_seen": false,
    "notes": []
  },
  "final_answer": "You have 3 pending invoices...",
  "elapsed_ms": 1234.56
}
```

**Key properties**:
- One JSON object per line (JSONL format)
- Parseable with standard JSON libraries
- Lightweight (summaries, not full outputs)
- Includes security audit trail (tenant_guard)
- Timestamped with UTC timezone
- Tracks performance (elapsed_ms)

### 🎯 Stage 3 Success Criteria - MET
✅ Created agent/tracing.py with JSONL trace writing
✅ Implemented write_trace() with automatic directory creation
✅ Implemented check_tenant_guard() with strict security rules
✅ Implemented summarize_output() to avoid storing sensitive data
✅ Integrated tracing into agent/main.py
✅ Preserved raw Responses API loop (no framework changes)
✅ Added timing tracking (elapsed_ms)
✅ Added tool call collection per turn
✅ Added context window hygiene (20 turn limit)
✅ Created comprehensive test suite (agent/test_tracing.py)
✅ All tests pass successfully
✅ Fixed linting issues (removed unused imports)
✅ Terminal output remains clean and readable
✅ Trace writing failures don't crash agent

### 🔧 Configuration
**Environment variables**:
- TRACE_PATH: Path to JSONL trace file (default: "evals/traces/agent_traces.jsonl")
- Configured in agent/config.py
- Used by agent/main.py for trace writing

**Context window settings**:
- MAX_HISTORY_TURNS = 20 (configurable in agent/main.py)
- Keeps developer prompt + last 20 user/assistant pairs
- Total messages: 41 (1 developer + 40 conversation)

## Next Steps - Stage 4 Planning
- [ ] Register skills as tools in TOOL_REGISTRY and TOOL_SCHEMAS (optional)
- [ ] Implement automated testing (unit tests for skills and tools)
- [ ] Add cross-tenant isolation tests
- [ ] Build multi-step workflow capabilities
- [ ] Build evaluation harness using traces
- [ ] Add trace analysis tools (violation detection, performance metrics)
