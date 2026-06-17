"""Minimal supplier agent using the OpenAI Responses API."""

import os

from dotenv import load_dotenv
from openai import DefaultHttpxClient, OpenAI

from agent.config import OPENAI_MODEL, SUPPLIER_NAME
from agent.tools import TOOL_SCHEMAS, TOOL_REGISTRY, execute_tool_call

load_dotenv()

http_client = DefaultHttpxClient(verify=False) if os.getenv("DISABLE_SSL_VERIFY") else None
client = OpenAI(http_client=http_client)

# TEMPLATE: Update accordingly
SYSTEM_PROMPT = f"""
You are a supplier-facing accounts receivable assistant for {SUPPLIER_NAME}.

Security and scope rules:
- You only help the configured active supplier.
- Never reveal invoices, purchase orders, contracts, catalog items, supplier profiles, or analytics for other suppliers.
- If the user asks about another named supplier, explain that you can only help with the active supplier account.
- Do not ask the user for supplier_id. The application enforces supplier scope.
- Do not reveal internal supplier_id values unless needed for debugging.
- Use tools for factual procurement data. Do not invent invoice statuses, PO statuses, dates, amounts, or contract terms.
- For ambiguous questions, summarize what is known from available tools and call out uncertainty.

Tool selection guidance:
- For exact invoice or PO lookups (e.g., "show me invoice 1001"), use get_invoice or get_purchase_order.
- For account health questions (e.g., "how is my account?", "what's my AR status?"), use get_ar_status.
- For follow-up questions (e.g., "what should I follow up on?", "what needs attention?"), use get_ar_status.
- For delivered POs without payment (e.g., "which delivered orders haven't been paid?"), use get_delivered_pos_without_paid_invoice.
- For cross-supplier named questions (e.g., "show me SteelWorks invoices"), refuse politely and scope to the active supplier only.
"""

def run_agent_loop():
    conversation = [{"role": "developer", "content": SYSTEM_PROMPT}]

    print("Supplier AR Agent (type 'quit' to exit)")
    print("-" * 40)

    while True:
        user_input = input("\nYou: ").strip()
        if not user_input or user_input.lower() in ("quit", "exit"):
            break

        conversation.append({"role": "user", "content": user_input})

        while True:
            response = client.responses.create(
                model=OPENAI_MODEL,
                input=conversation,
                tools=TOOL_SCHEMAS,
            )

            has_tool_calls = False
            for item in response.output:
                if item.type == "function_call":
                    has_tool_calls = True
                    result = execute_tool_call(item, TOOL_REGISTRY)
                    conversation.append(item)
                    conversation.append(
                        {"type": "function_call_output", "call_id": item.call_id, "output": result}
                    )

            if not has_tool_calls:
                break

        print(f"\nAssistant: {response.output_text}")
        conversation.append({"role": "assistant", "content": response.output_text})


if __name__ == "__main__":
    run_agent_loop()
