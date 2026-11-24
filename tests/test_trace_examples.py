"""Offline checks for the two persisted agent/tool traces (no external service)."""
import json

from src.trace_examples import build_trace, write_traces


def test_success_has_tool_observation_and_stop():
    trace = build_trace(inject_temporary_failure=False)
    assert trace["scenario"] == "success"
    assert [step["decision"] for step in trace["timeline"]] == [
        "call_tool", "execute_and_observe", "final_answer"
    ]
    assert trace["timeline"][1]["observation"]["status"] == "ok"
    assert trace["timeline"][2]["stop_reason"] == "model_returned_message"
    assert trace["tool_trace"][0]["attempts"] == 1


def test_transient_failure_records_exhaustion_and_a_safe_answer():
    trace = build_trace(inject_temporary_failure=True)
    observation = trace["timeline"][1]["observation"]
    assert observation["error"]["type"] == "service_unavailable"
    assert observation["error"]["retryable"] is True
    assert trace["tool_trace"][0]["attempts"] == 3
    assert trace["agent_audit"][0]["error_type"] == "service_unavailable"
    assert "לא בוצע שינוי" in trace["final_result"]["answer"]


def test_two_scenarios_keep_all_six_original_mock_bookings():
    for fail in (False, True):
        trace = build_trace(inject_temporary_failure=fail)
        assert trace["reservations_before"] == trace["reservations_after"] == 6
        assert trace["backend_calls"] == (3 if fail else 2)


def test_scenario_marked_as_scripted_not_real_llm():
    for fail in (False, True):
        trace = build_trace(inject_temporary_failure=fail)
        assert "NOT a real LLM" in trace["simulation_notice"]
        assert "ScriptedModel" in trace["setup"]["decision_provider"]
        assert trace["assessment"]["did_model_understand_hebrew"].startswith("Not tested")


def test_trace_files_are_generated_and_parseable(tmp_path):
    paths = write_traces(tmp_path)
    assert set(paths) == {"success", "transient_failure"}
    for scenario, path in paths.items():
        assert path.exists()
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["scenario"] == scenario
        assert payload["agent_audit"][-1]["decision"] == "answer"


def test_trace_timeline_matches_tool_trace_and_agent_audit():
    for fail in (False, True):
        trace = build_trace(inject_temporary_failure=fail)
        assert trace["timeline"][0]["tool"] == trace["tool_trace"][0]["tool"]
        assert trace["timeline"][1]["attempts"] == trace["tool_trace"][0]["attempts"]
        assert trace["agent_audit"][0]["decision"] == "tool_result"
        assert trace["agent_audit"][1]["decision"] == "answer"
