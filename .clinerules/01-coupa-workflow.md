# Coupa Supplier AR Agent workflow rules

## Challenge constraints
- Use OpenAI Responses API only: client.responses.create().
- No agent frameworks: no LangChain, LangGraph, CrewAI, AutoGen, etc.
- Tools must call the mock procurement API over HTTP via httpx.
- Do not import from api/ inside agent tools.
- Do not modify api/.
- Production diff should touch only agent/ and evals/.

## Workflow
- Before non-trivial code, update agent/NOTES.md with intent, plan, invariants, known limits, and verification.
- No app code before the plan exists.
- Keep business rules deterministic when possible. Do not ask the LLM to compute facts that Python can compute exactly.
- Prefer small tool modules with one API capability per function.

## Tenancy and security
- The active supplier is configured in code/env as SUPPLIER_ID.
- supplier_id must never be exposed as a tool schema argument.
- Every API call that supports supplier_id must inject the configured SUPPLIER_ID in code.
- Do not build list_all_suppliers, search_suppliers, or generic get_supplier(id).
- If a supplier profile tool is needed, expose get_my_supplier_profile() only and pin the path to SUPPLIER_ID.
- Treat questions about other suppliers as out-of-scope unless the question can be answered without exposing their data.
- Never return records whose supplier_id differs from the configured SUPPLIER_ID.

## Quality bar
- Run ruff and mypy before commit.
- Add at least smoke-level tests or eval assertions for positive and negative cases.
- Produce structured traces, not print-only logs.
- Update agent/NOTES.md before commit.