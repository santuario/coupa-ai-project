"""Minimal supplier agent using the OpenAI Responses API."""

import json
import os
import time
from typing import Any, cast

from dotenv import load_dotenv
from openai import DefaultHttpxClient, OpenAI

from agent.config import OPENAI_MODEL, SUPPLIER_NAME, SUPPLIER_ID, TRACE_PATH
from agent.tools import TOOL_SCHEMAS, TOOL_REGISTRY, execute_tool_call
from agent.tracing import write_trace

load_dotenv()

http_client = DefaultHttpxClient(verify=False) if os.getenv("DISABLE_SSL_VERIFY") else None
client = OpenAI(http_client=http_client)

# TEMPLATE: Update accordingly
SYSTEM_PROMPT = f"""
You are a supplier-facing accounts receivable assistant for {SUPPLIER_NAME}.

Security and scope rules:
- You only help the configured active supplier ({SUPPLIER_NAME}).
- Never reveal invoices, purchase orders, contracts, catalog items, supplier profiles, or analytics for other suppliers.
- If the user asks about another named supplier, refuse politely and explain that you can only help with the active supplier account ({SUPPLIER_NAME}).
- In refusals, NEVER repeat or mention the name of any other supplier, company, or forbidden term from the user's question. Do not echo forbidden terms (such as other supplier names, "pending", etc.) in your refusal or answer.
- Always include the active supplier name ("{SUPPLIER_NAME}") in all in-scope answers and in any refusal or scoping statement.
- Use refusal templates such as: "I can only help with the active supplier account ({SUPPLIER_NAME})." or "Sorry, I can only provide information for the active supplier account."
- Do not ask the user for supplier_id. The application enforces supplier scope.
- Do not reveal internal supplier_id values unless needed for debugging.
- Use tools for factual procurement data. Do not invent invoice statuses, PO statuses, dates, amounts, or contract terms.
- For ambiguous questions, summarize what is known from available tools and call out uncertainty.
- For in-scope answers, always mention "{SUPPLIER_NAME}" at least once in your response.

Tool selection guidance:
- For exact invoice or PO lookups (e.g., "show me invoice 1001"), use get_invoice or get_purchase_order.
- For account health questions (e.g., "how is my account?", "what's my AR status?"), use get_ar_status.
- For follow-up questions (e.g., "what should I follow up on?", "what needs attention?"), use get_ar_status.
- For delivered POs without payment (e.g., "which delivered orders haven't been paid?"), use get_delivered_pos_without_paid_invoice.
- For cross-supplier named questions (e.g., "show me SteelWorks invoices"), refuse politely and scope to the active supplier only, without repeating the other supplier's name or forbidden terms.
"""


def run_agent_turn(user_input: str, conversation: list[Any] | None = None) -> dict[str, Any]:
    """
    Run a single agent turn with the given user input.

    Args:
        user_input: The user's question or command.
        conversation: Optional existing conversation history. If None, starts fresh.

    Returns:
        dict with keys:
            - final_answer: str
            - tool_calls: list[dict]
            - conversation: list (updated conversation history)
            - elapsed_ms: float
    """
    # Initialize conversation if not provided
    if conversation is None:
        developer_prompt = {"role": "developer", "content": SYSTEM_PROMPT}
        conversation = [developer_prompt]

    # Start timing for this turn
    turn_start_time = time.time()

    # Track tool calls for this turn
    turn_tool_calls: list[dict[str, Any]] = []

    conversation.append({"role": "user", "content": user_input})

    # Tool execution loop
    while True:
        response = client.responses.create(
            model=OPENAI_MODEL,
            input=conversation,
            tools=cast(Any, TOOL_SCHEMAS),
        )

        has_tool_calls = False

        for item in response.output:
            if item.type == "function_call":
                has_tool_calls = True
                result = execute_tool_call(item, TOOL_REGISTRY)

                # Track this tool call for tracing
                try:
                    args = json.loads(item.arguments) if item.arguments else {}
                except json.JSONDecodeError:
                    args = {}

                turn_tool_calls.append(
                    {
                        "name": item.name,
                        "arguments": args,
                        "output": result,
                        "status": "success",
                    }
                )

                conversation.append(item)
                conversation.append(
                    {
                        "type": "function_call_output",
                        "call_id": item.call_id,
                        "output": result,
                    }
                )

        if not has_tool_calls:
            break

    # Calculate elapsed time
    elapsed_ms = (time.time() - turn_start_time) * 1000

    # Add assistant response to conversation
    conversation.append({"role": "assistant", "content": response.output_text})

    return {
        "final_answer": response.output_text,
        "tool_calls": turn_tool_calls,
        "conversation": conversation,
        "elapsed_ms": elapsed_ms,
    }


def run_agent_loop() -> None:
    """Interactive CLI loop for the agent."""
    # Keep developer prompt separate for context window hygiene
    developer_prompt = {"role": "developer", "content": SYSTEM_PROMPT}
    conversation: list[Any] = [developer_prompt]

    # Maximum conversation history to keep, excluding developer prompt
    MAX_HISTORY_TURNS = 20

    print("Supplier AR Agent (type 'quit' to exit)")
    print("-" * 40)

    while True:
        user_input = input("\nYou: ").strip()
        if not user_input or user_input.lower() in ("quit", "exit"):
            break

        # Run a single turn
        result = run_agent_turn(user_input, conversation)

        # Update conversation from result
        conversation = result["conversation"]

        # Display response
        print(f"\nAssistant: {result['final_answer']}")

        # Write trace for this turn
        try:
            write_trace(
                trace_path=TRACE_PATH,
                model=OPENAI_MODEL,
                active_supplier_name=SUPPLIER_NAME,
                user_message=user_input,
                tool_calls=result["tool_calls"],
                final_answer=result["final_answer"],
                elapsed_ms=result["elapsed_ms"],
                active_supplier_id=SUPPLIER_ID,
            )
        except Exception as e:
            print(f"[Warning: Failed to write trace: {e}]")

        # Context window hygiene: keep developer prompt + recent history.
        # Remove oldest user/assistant pair if we exceed the limit.
        if len(conversation) > (MAX_HISTORY_TURNS * 2 + 1):  # +1 for developer prompt
            conversation = [conversation[0]] + conversation[3:]


if __name__ == "__main__":
    run_agent_loop()