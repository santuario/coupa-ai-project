"""
Evaluation harness for supplier AR agent.

Loads questions.json and expectations.json, runs each question through the agent,
and validates responses against expected behavior.
"""

import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.main import run_agent_turn
from agent.config import SUPPLIER_ID, SUPPLIER_NAME
from agent.tracing import check_tenant_guard


def load_json(filepath: str) -> dict | list:
    """Load JSON file."""
    with open(filepath, "r") as f:
        return json.load(f)


def check_required_terms(text: str, required_terms: list[str]) -> tuple[bool, list[str]]:
    """
    Check if all required terms appear in text (case-insensitive).
    
    Returns:
        (all_found: bool, missing_terms: list[str])
    """
    text_lower = text.lower()
    missing = []
    for term in required_terms:
        if term.lower() not in text_lower:
            missing.append(term)
    return len(missing) == 0, missing


def check_forbidden_terms(text: str, forbidden_terms: list[str]) -> tuple[bool, list[str]]:
    """
    Check if any forbidden terms appear in text (case-insensitive).
    
    Returns:
        (none_found: bool, found_terms: list[str])
    """
    text_lower = text.lower()
    found = []
    for term in forbidden_terms:
        if term.lower() in text_lower:
            found.append(term)
    return len(found) == 0, found


def check_supplier_id_in_args(tool_calls: list[dict]) -> tuple[bool, list[str]]:
    """
    Check if supplier_id appears in any tool call arguments.
    
    Returns:
        (none_found: bool, violations: list[str])
    """
    violations = []
    for call in tool_calls:
        if "supplier_id" in call.get("arguments", {}):
            violations.append(f"Tool '{call['name']}' has supplier_id in arguments")
    return len(violations) == 0, violations


def run_evaluation() -> dict:
    """
    Run evaluation on all questions.
    
    Returns:
        dict with evaluation results
    """
    # Load questions and expectations
    questions_path = Path(__file__).parent / "questions.json"
    expectations_path = Path(__file__).parent / "expectations.json"
    
    questions = load_json(str(questions_path))
    expectations = load_json(str(expectations_path))
    
    results = {
        "supplier_id": SUPPLIER_ID,
        "supplier_name": SUPPLIER_NAME,
        "total_questions": len(questions),
        "passed": 0,
        "failed": 0,
        "questions": []
    }
    
    print(f"Running evaluation for {SUPPLIER_NAME} (SUPPLIER_ID={SUPPLIER_ID})")
    print(f"Total questions: {len(questions)}")
    print("=" * 80)
    
    for question_obj in questions:
        question_id = str(question_obj["id"])
        question_text = question_obj["question"]
        category = question_obj["category"]
        
        print(f"\nQuestion {question_id}: {question_text}")
        print(f"Category: {category}")
        
        # Get expectations for this question
        expectation = expectations.get(question_id, {})
        expected_scope = expectation.get("expected_scope", "unknown")
        expected_behavior = expectation.get("expected_behavior", "unknown")
        required_terms = expectation.get("required_terms", [])
        forbidden_terms = expectation.get("forbidden_terms", [])
        
        print(f"Expected: {expected_scope} / {expected_behavior}")
        
        # Run agent turn
        try:
            result = run_agent_turn(question_text, conversation=None)
            final_answer = result["final_answer"]
            tool_calls = result["tool_calls"]
            elapsed_ms = result["elapsed_ms"]
            
            print(f"Agent response: {final_answer[:100]}...")
            print(f"Tool calls: {len(tool_calls)}")
            
            # Initialize test results
            test_result = {
                "question_id": question_id,
                "question": question_text,
                "category": category,
                "expected_scope": expected_scope,
                "expected_behavior": expected_behavior,
                "final_answer": final_answer,
                "tool_calls": [{"name": tc["name"], "arguments": tc["arguments"]} for tc in tool_calls],
                "elapsed_ms": elapsed_ms,
                "checks": {},
                "passed": True,
                "failures": []
            }
            
            # Check 1: Required terms
            if required_terms:
                all_found, missing = check_required_terms(final_answer, required_terms)
                test_result["checks"]["required_terms"] = {
                    "passed": all_found,
                    "required": required_terms,
                    "missing": missing
                }
                if not all_found:
                    test_result["passed"] = False
                    test_result["failures"].append(f"Missing required terms: {missing}")
                    print(f"  ❌ Missing required terms: {missing}")
                else:
                    print("  ✅ All required terms found")
            
            # Check 2: Forbidden terms
            if forbidden_terms:
                none_found, found = check_forbidden_terms(final_answer, forbidden_terms)
                test_result["checks"]["forbidden_terms"] = {
                    "passed": none_found,
                    "forbidden": forbidden_terms,
                    "found": found
                }
                if not none_found:
                    test_result["passed"] = False
                    test_result["failures"].append(f"Found forbidden terms: {found}")
                    print(f"  ❌ Found forbidden terms: {found}")
                else:
                    print("  ✅ No forbidden terms found")
            
            # Check 3: supplier_id in tool arguments
            no_supplier_id, violations = check_supplier_id_in_args(tool_calls)
            test_result["checks"]["supplier_id_in_args"] = {
                "passed": no_supplier_id,
                "violations": violations
            }
            if not no_supplier_id:
                test_result["passed"] = False
                test_result["failures"].append(f"supplier_id in tool arguments: {violations}")
                print(f"  ❌ supplier_id in tool arguments: {violations}")
            else:
                print("  ✅ No supplier_id in tool arguments")
            
            # Check 4: Tenant guard (cross-tenant records)
            tenant_guard = check_tenant_guard(tool_calls, SUPPLIER_ID)
            test_result["checks"]["tenant_guard"] = {
                "passed": not tenant_guard["cross_tenant_records_seen"],
                "supplier_id_in_args": tenant_guard["supplier_id_in_args"],
                "cross_tenant_records_seen": tenant_guard["cross_tenant_records_seen"],
                "notes": tenant_guard["notes"]
            }
            if tenant_guard["cross_tenant_records_seen"]:
                test_result["passed"] = False
                test_result["failures"].append(f"Cross-tenant records detected: {tenant_guard['notes']}")
                print("  ❌ Cross-tenant records detected")
            else:
                print("  ✅ No cross-tenant records detected")
            
            # Update overall results
            if test_result["passed"]:
                results["passed"] += 1
                print("  ✅ PASSED")
            else:
                results["failed"] += 1
                print("  ❌ FAILED")
            
            results["questions"].append(test_result)
            
        except Exception as e:
            print(f"  ❌ ERROR: {e}")
            test_result = {
                "question_id": question_id,
                "question": question_text,
                "category": category,
                "expected_scope": expected_scope,
                "expected_behavior": expected_behavior,
                "error": str(e),
                "passed": False,
                "failures": [f"Exception: {e}"]
            }
            results["failed"] += 1
            results["questions"].append(test_result)
    
    print("\n" + "=" * 80)
    print("EVALUATION COMPLETE")
    print(f"Passed: {results['passed']}/{results['total_questions']}")
    print(f"Failed: {results['failed']}/{results['total_questions']}")
    print(f"Success rate: {results['passed']/results['total_questions']*100:.1f}%")
    
    return results


def main():
    """Main entry point."""
    # Run evaluation
    results = run_evaluation()
    
    # Write results to file
    results_path = Path(__file__).parent / "results.json"
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\nResults written to: {results_path}")
    
    # Exit with appropriate code
    sys.exit(0 if results["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
