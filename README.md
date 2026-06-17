# Supplier AR Agent

A supplier-facing accounts-receivable agent built on the provided mock procurement
API. The agent helps a single supplier understand its invoices, purchase orders,
contracts, overdue items, and overall account health. Built with the OpenAI
Responses API and a raw tool-use loop (no agent frameworks).

## Running

```bash
# 1. Install
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add your OPENAI_API_KEY and set SUPPLIER_ID

# 2. Start the mock API (separate terminal)
uvicorn api.main:app --reload

# 3. Run the agent
SUPPLIER_ID=1 python -m agent.main

# 4. Run the eval harness
SUPPLIER_ID=1 python -m evals.run_evals
```

The agent refuses to start without `SUPPLIER_ID` set — an unscoped AR agent could
read every supplier's data, so the tenant scope is mandatory at boot.

## What's implemented

- **Stage 1 — Tools:** scoped invoice, purchase-order, contract, and overdue-summary
  tools. The unsafe reference `get_invoices` was rewritten to enforce tenancy.
- **Stage 2 — Skills:** two deterministic composite skills (`get_ar_status`,
  `get_delivered_pos_without_paid_invoice`) that orchestrate multiple endpoints in
  code rather than letting the model chain calls.
- **Stage 3 — Traces:** every turn writes parseable JSONL with tool calls, latency,
  and an automatic tenant-guard check. `agent/analyze_traces.py` reads them back.
- **Stages 4–5 — Evals:** `evals/run_evals.py` runs the question set with two
  assertion classes (in-tenant correctness, out-of-tenant refusal) and writes a
  pass/fail report. Currently 12/12.

## Architecture

```
agent/

config.py            — session config; fails fast if SUPPLIER_ID is unset

api_client.py        — single HTTP client; injects supplier_id on every call

tools.py             — tool registry + dispatcher

procurement_tools/   — one module per resource

invoices.py        — invoice tools (the unsafe reference, rewritten)

purchase_orders.py — PO tools

contracts.py       — contract tools

analytics.py       — scoped overdue-summary tool

skills.py            — deterministic multi-endpoint compositions

tracing.py           — per-turn JSONL traces + tenant guard

test_tracing.py      — tests for the tracing + tenant-guard logic

main.py              — raw Responses API tool loop

evals/

questions.json       — provided question set

expectations.json    — per-question expected behavior (in/out of tenant)

run_evals.py         — eval harness (12/12)

traces/              — JSONL turn traces written at runtime

.clinerules            — operating rules enforced while building with the AI companion

NOTES.md               — task journal (decisions, findings, fixes)
```

The shape: the model proposes (which tool, what intent), the harness disposes
(tenancy, composition, execution). The LLM never holds authority it shouldn't.

## Decisions & Tradeoffs

**Tenancy is enforced in the harness, and not assumed of the API.** I read the
routers before writing the agent and found tenancy is asymmetric: `/invoices`,
`/contracts`, `/purchase-orders`, and `/analytics/*` filter by a `supplier_id`
query param, but `/suppliers/{id}` ignores scope and returns any supplier by ID.
So `supplier_id` never appears in a tool schema — the model can't name another
supplier because it has no field to do so. `api_client` injects it on every call,
and I expose no arbitrary supplier-by-ID lookup.

**Skills are deterministic compositions, not model-chained tool calls.** For
account-health and reconciliation questions, letting the model chain four tool
calls burns tokens and risks mid-task drift. The skills run the sequence in Python
and return only a shaped summary, which keeps the parent agent in control of the
outcome and bounds context-window growth.

**Traces double as a security auditor.** Each turn's trace runs a tenant guard
that flags two things: `supplier_id` appearing in tool arguments (it never should),
and any returned record whose `supplier_id` differs from the active one. Observability
and the tenancy invariant are checked in the same place, on every turn.

**Unified the "overdue" definition across tools and skills.** The API has two
notions of overdue: the literal `status` field, and the analytics definition
(`status == overdue` OR a pending invoice past its `due_date`). These initially
disagreed (one tool said 2 overdue, the skill said 5). I unified on the analytics
definition — a pending invoice past due is functionally overdue regardless of the
stored flag, which is exactly what an AR agent should catch. I also guarded the
`get_invoices` tool so that when `overdue=true` is requested, any `status` filter
the model adds is dropped, because the API applies status first and would otherwise
narrow to a wrong subset.

**Cross-tenant lookups fail as "not found," not "exists but forbidden."** When the
agent is asked about an invoice belonging to another supplier, the scoped API
returns 404 and the agent says it couldn't find it. This is deliberate: confirming
"that invoice exists but isn't yours" would itself leak that the ID is valid in
another tenant. "Not found" is the safe answer, not just the simple one.

**Tools deliberately not built:** supplier listing, supplier-by-ID, catalog search.
A supplier shouldn't see other suppliers, and `/suppliers/{id}` has no scope — so
exposing any of these would open a leak.

## What I'd harden first in v2

- **Human confirmation before write operations.** `create_invoice` and
  `acknowledge_purchase_order` go through the scoped client, so they can't touch
  another supplier — but a money-affecting write should hit a confirmation gate
  before executing, mirroring a human-in-the-loop checkpoint.
- **Parallelize the skill's endpoint calls.** `get_ar_status` fetches four
  endpoints sequentially for simplicity; they're independent and could run
  concurrently with asyncio.
- **A single overdue concept agent-wide.** The tool and skill now agree, but
  exposing one canonical overdue notion would remove the chance of two numbers for
  one word entirely.
- **Refusal assertions keyed on leaked data, not supplier names.** The eval
  currently checks that another supplier's name is absent; keying on leaked amounts
  and IDs instead would remove false-negative risk if a correct refusal names the
  out-of-tenant supplier.

## Notes

- Tenancy is enforced only in the agent layer; the mock API has no auth.
- Created invoices reset when the API restarts (in-memory store).
- Evals use pragmatic term-based assertions, not full semantic grading.