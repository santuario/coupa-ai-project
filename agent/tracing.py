"""JSONL trace writing for agent conversation turns.

This module provides lightweight tracing functionality that writes one JSON object
per conversation turn to a JSONL file. Each trace includes timing, model info,
tool calls with summaries, tenant guard results, and the final answer.

Rules:
- Do not store full sensitive raw outputs; store summaries and guard results
- Write one JSON object per conversation turn
- Automatic directory creation
- Lightweight; no external tracing service
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypedDict


class ToolCallTrace(TypedDict):
    """Trace information for a single tool call."""
    name: str
    arguments: dict[str, Any]
    output_summary: str
    status: str


class TenantGuardTrace(TypedDict):
    """Tenant guard security check results."""
    supplier_id_in_args: bool
    cross_tenant_records_seen: bool
    notes: list[str]


class ConversationTurnTrace(TypedDict):
    """Complete trace for a single conversation turn."""
    timestamp: str
    model: str
    active_supplier_name: str
    user_message: str
    tool_calls: list[ToolCallTrace]
    tenant_guard: TenantGuardTrace
    final_answer: str
    elapsed_ms: float


def ensure_trace_directory(trace_path: str) -> None:
    """Ensure the directory for the trace file exists."""
    directory = os.path.dirname(trace_path)
    if directory:
        Path(directory).mkdir(parents=True, exist_ok=True)


def summarize_output(output: str, max_length: int = 200) -> str:
    """Create a summary of tool output, avoiding full sensitive data.
    
    Args:
        output: The raw tool output string
        max_length: Maximum length of the summary
        
    Returns:
        A truncated or summarized version of the output
    """
    if not output:
        return ""
    
    # Try to parse as JSON and provide structured summary
    try:
        data = json.loads(output)
        if isinstance(data, list):
            return f"[List with {len(data)} items]"
        elif isinstance(data, dict):
            keys = list(data.keys())
            return f"{{Dict with keys: {', '.join(keys[:5])}{', ...' if len(keys) > 5 else ''}}}"
        else:
            return str(data)[:max_length]
    except (json.JSONDecodeError, TypeError):
        # Not JSON, just truncate
        if len(output) > max_length:
            return output[:max_length] + "..."
        return output


def check_tenant_guard(
    tool_calls: list[dict[str, Any]],
    active_supplier_id: int,
) -> TenantGuardTrace:
    """Analyze tool calls for tenant isolation violations.
    
    New rules:
    - supplier_id must NOT be present in tool arguments (application enforces scope)
    - All records in parsed JSON outputs must have supplier_id == active_supplier_id
    - If parsing fails, record as "unknown" status, not pass
    
    Args:
        tool_calls: List of tool call information with arguments and outputs
        active_supplier_id: The supplier ID that should be in scope
        
    Returns:
        TenantGuardTrace with security check results
    """
    supplier_id_in_args = False
    cross_tenant_records_seen = False
    notes: list[str] = []
    
    for tool_call in tool_calls:
        tool_name = tool_call.get("name", "unknown")
        args = tool_call.get("arguments", {})
        
        # RULE 1: supplier_id must NOT be in arguments
        if "supplier_id" in args:
            supplier_id_in_args = True
            cross_tenant_records_seen = True
            notes.append(
                f"VIOLATION: Tool '{tool_name}' has supplier_id in arguments. "
                f"Application should enforce scope, not pass supplier_id explicitly."
            )
        
        # RULE 2: Check output for tenant isolation
        output = tool_call.get("output", "")
        if output and isinstance(output, str):
            try:
                output_data = json.loads(output)
                
                # Check single dict with supplier_id
                if isinstance(output_data, dict) and "supplier_id" in output_data:
                    if output_data["supplier_id"] != active_supplier_id:
                        cross_tenant_records_seen = True
                        notes.append(
                            f"VIOLATION: Tool '{tool_name}' returned record with supplier_id="
                            f"{output_data['supplier_id']}, expected {active_supplier_id}"
                        )
                
                # Check list of records with supplier_id
                elif isinstance(output_data, list):
                    for idx, item in enumerate(output_data):
                        if isinstance(item, dict) and "supplier_id" in item:
                            if item["supplier_id"] != active_supplier_id:
                                cross_tenant_records_seen = True
                                notes.append(
                                    f"VIOLATION: Tool '{tool_name}' returned record at index {idx} "
                                    f"with supplier_id={item['supplier_id']}, expected {active_supplier_id}"
                                )
                                # Report all violations, not just first
            
            except (json.JSONDecodeError, TypeError) as e:
                # RULE 3: Parsing failures are recorded as unknown, not pass
                notes.append(
                    f"UNKNOWN: Tool '{tool_name}' output could not be parsed as JSON. "
                    f"Cannot verify tenant isolation. Error: {type(e).__name__}"
                )
    
    return TenantGuardTrace(
        supplier_id_in_args=supplier_id_in_args,
        cross_tenant_records_seen=cross_tenant_records_seen,
        notes=notes,
    )


def write_trace(
    trace_path: str,
    model: str,
    active_supplier_name: str,
    user_message: str,
    tool_calls: list[dict[str, Any]],
    final_answer: str,
    elapsed_ms: float,
    active_supplier_id: int,
) -> None:
    """Write a conversation turn trace to the JSONL file.
    
    Args:
        trace_path: Path to the JSONL trace file
        model: Model name used for this turn
        active_supplier_name: Name of the active supplier
        user_message: The user's input message
        tool_calls: List of tool calls with name, arguments, output, and status
        final_answer: The final response to the user
        elapsed_ms: Time elapsed for this turn in milliseconds
        active_supplier_id: The supplier ID that should be in scope
    """
    ensure_trace_directory(trace_path)
    
    # Create tool call traces with summaries
    tool_call_traces: list[ToolCallTrace] = []
    for tc in tool_calls:
        tool_call_traces.append(
            ToolCallTrace(
                name=tc.get("name", "unknown"),
                arguments=tc.get("arguments", {}),
                output_summary=summarize_output(tc.get("output", "")),
                status=tc.get("status", "success"),
            )
        )
    
    # Run tenant guard checks
    tenant_guard = check_tenant_guard(tool_calls, active_supplier_id)
    
    # Create the complete trace
    trace = ConversationTurnTrace(
        timestamp=datetime.now(timezone.utc).isoformat(),
        model=model,
        active_supplier_name=active_supplier_name,
        user_message=user_message,
        tool_calls=tool_call_traces,
        tenant_guard=tenant_guard,
        final_answer=final_answer,
        elapsed_ms=elapsed_ms,
    )
    
    # Append to JSONL file
    with open(trace_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(trace) + "\n")


def read_traces(trace_path: str) -> list[ConversationTurnTrace]:
    """Read all traces from a JSONL file.
    
    Args:
        trace_path: Path to the JSONL trace file
        
    Returns:
        List of conversation turn traces
    """
    if not os.path.exists(trace_path):
        return []
    
    traces: list[ConversationTurnTrace] = []
    with open(trace_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                traces.append(json.loads(line))
    
    return traces
