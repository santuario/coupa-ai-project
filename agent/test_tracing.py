"""Test script for the tracing module."""

import json
import os
import tempfile

from agent.tracing import write_trace, read_traces, summarize_output, check_tenant_guard


def test_summarize_output():
    """Test output summarization."""
    print("Testing summarize_output...")
    
    # Test with JSON list
    output = json.dumps([{"id": 1}, {"id": 2}, {"id": 3}])
    summary = summarize_output(output)
    assert "[List with 3 items]" == summary, f"Expected list summary, got: {summary}"
    
    # Test with JSON dict
    output = json.dumps({"invoice_id": 1001, "amount": 5000, "status": "paid"})
    summary = summarize_output(output)
    assert "Dict with keys:" in summary, f"Expected dict summary, got: {summary}"
    
    # Test with long string
    output = "x" * 300
    summary = summarize_output(output, max_length=200)
    assert len(summary) <= 203, f"Summary too long: {len(summary)}"  # 200 + "..."
    assert summary.endswith("..."), "Long string should be truncated with ..."
    
    print("✓ summarize_output tests passed")


def test_tenant_guard():
    """Test tenant guard checks with new rules."""
    print("\nTesting check_tenant_guard...")
    
    # Test 1: supplier_id in arguments is a VIOLATION (even if correct)
    tool_calls = [
        {
            "name": "get_invoices",
            "arguments": {"supplier_id": 1},
            "output": json.dumps([{"invoice_id": 1001, "supplier_id": 1}]),
        }
    ]
    result = check_tenant_guard(tool_calls, active_supplier_id=1)
    assert result["supplier_id_in_args"] is True
    assert result["cross_tenant_records_seen"] is True  # Now a violation
    assert len(result["notes"]) > 0
    assert "VIOLATION" in result["notes"][0]
    
    # Test 2: No supplier_id in arguments, correct output - PASS
    tool_calls = [
        {
            "name": "get_invoices",
            "arguments": {"status": "pending"},
            "output": json.dumps([{"invoice_id": 1001, "supplier_id": 1}]),
        }
    ]
    result = check_tenant_guard(tool_calls, active_supplier_id=1)
    assert result["supplier_id_in_args"] is False
    assert result["cross_tenant_records_seen"] is False
    assert len(result["notes"]) == 0
    
    # Test 3: Cross-tenant data in output - VIOLATION
    tool_calls = [
        {
            "name": "get_invoices",
            "arguments": {},
            "output": json.dumps([{"invoice_id": 1001, "supplier_id": 2}]),
        }
    ]
    result = check_tenant_guard(tool_calls, active_supplier_id=1)
    assert result["cross_tenant_records_seen"] is True
    assert len(result["notes"]) > 0
    assert "VIOLATION" in result["notes"][0]
    
    # Test 4: Multiple violations in list
    tool_calls = [
        {
            "name": "get_invoices",
            "arguments": {},
            "output": json.dumps([
                {"invoice_id": 1001, "supplier_id": 1},
                {"invoice_id": 1002, "supplier_id": 2},
                {"invoice_id": 1003, "supplier_id": 3},
            ]),
        }
    ]
    result = check_tenant_guard(tool_calls, active_supplier_id=1)
    assert result["cross_tenant_records_seen"] is True
    assert len(result["notes"]) == 2  # Two violations
    
    # Test 5: Parsing failure - UNKNOWN
    tool_calls = [
        {
            "name": "get_invoices",
            "arguments": {},
            "output": "This is not JSON",
        }
    ]
    result = check_tenant_guard(tool_calls, active_supplier_id=1)
    assert len(result["notes"]) > 0
    assert "UNKNOWN" in result["notes"][0]
    
    # Test 6: Empty output - no notes
    tool_calls = [
        {
            "name": "get_invoices",
            "arguments": {},
            "output": json.dumps([]),
        }
    ]
    result = check_tenant_guard(tool_calls, active_supplier_id=1)
    assert result["supplier_id_in_args"] is False
    assert result["cross_tenant_records_seen"] is False
    assert len(result["notes"]) == 0
    
    print("✓ check_tenant_guard tests passed")


def test_write_and_read_trace():
    """Test writing and reading traces."""
    print("\nTesting write_trace and read_traces...")
    
    # Create a temporary directory for traces
    with tempfile.TemporaryDirectory() as tmpdir:
        trace_path = os.path.join(tmpdir, "test_traces", "agent_traces.jsonl")
        
        # Write a trace
        tool_calls = [
            {
                "name": "get_invoices",
                "arguments": {"supplier_id": 1, "status": "pending"},
                "output": json.dumps([{"invoice_id": 1001, "amount": 5000}]),
                "status": "success",
            }
        ]
        
        write_trace(
            trace_path=trace_path,
            model="gpt-5.4",
            active_supplier_name="Acme Technology Solutions",
            user_message="Show me pending invoices",
            tool_calls=tool_calls,
            final_answer="You have 1 pending invoice for $5000.",
            elapsed_ms=1234.56,
            active_supplier_id=1,
        )
        
        # Verify file was created
        assert os.path.exists(trace_path), f"Trace file not created at {trace_path}"
        
        # Read the trace back
        traces = read_traces(trace_path)
        assert len(traces) == 1, f"Expected 1 trace, got {len(traces)}"
        
        trace = traces[0]
        assert trace["model"] == "gpt-5.4"
        assert trace["active_supplier_name"] == "Acme Technology Solutions"
        assert trace["user_message"] == "Show me pending invoices"
        assert trace["final_answer"] == "You have 1 pending invoice for $5000."
        assert trace["elapsed_ms"] == 1234.56
        assert len(trace["tool_calls"]) == 1
        assert trace["tool_calls"][0]["name"] == "get_invoices"
        assert trace["tool_calls"][0]["status"] == "success"
        assert "timestamp" in trace
        
        # Write another trace
        write_trace(
            trace_path=trace_path,
            model="gpt-5.4",
            active_supplier_name="Acme Technology Solutions",
            user_message="What is my AR status?",
            tool_calls=[],
            final_answer="Your account is in good standing.",
            elapsed_ms=567.89,
            active_supplier_id=1,
        )
        
        # Read both traces
        traces = read_traces(trace_path)
        assert len(traces) == 2, f"Expected 2 traces, got {len(traces)}"
        
        print("✓ write_trace and read_traces tests passed")


def test_directory_creation():
    """Test automatic directory creation."""
    print("\nTesting automatic directory creation...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Use a deeply nested path that doesn't exist
        trace_path = os.path.join(tmpdir, "a", "b", "c", "traces.jsonl")
        
        write_trace(
            trace_path=trace_path,
            model="gpt-5.4",
            active_supplier_name="Test Supplier",
            user_message="Test message",
            tool_calls=[],
            final_answer="Test answer",
            elapsed_ms=100.0,
            active_supplier_id=1,
        )
        
        assert os.path.exists(trace_path), "Nested directories not created"
        
        print("✓ Directory creation test passed")


def main():
    """Run all tests."""
    print("=" * 60)
    print("Running tracing module tests")
    print("=" * 60)
    
    test_summarize_output()
    test_tenant_guard()
    test_write_and_read_trace()
    test_directory_creation()
    
    print("\n" + "=" * 60)
    print("✓ All tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
