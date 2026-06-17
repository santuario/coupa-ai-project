# Task Journal - Supplier AR Agent

Status: IN PROGRESS
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
- Use a scoped API client to centralize supplier_id injection.
- Keep supplier_id out of all tool schemas.
- Use deterministic Python skills for account health and follow-up reasoning.
- Use model for language synthesis, not tenant filtering.

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