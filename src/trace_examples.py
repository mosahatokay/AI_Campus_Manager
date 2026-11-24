"""Produce reproducible, offline CampusAI agent/tool traces for milestone 1.

Usage: python -m src.trace_examples

IMPORTANT: ScriptedModel is a deterministic TEST DOUBLE, not a language model.
The examples do not call SQL Server, Colab, a paid API, or any real service.
"""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from .agent import CampusAgent
from .agent_models import ScriptedModel
from .mock_backend import MockBackend
from .tools import CampusTools

ROOT = Path(__file__).resolve().parent.parent
TRACE_DIRECTORY = ROOT / "docs" / "traces"

REQUEST = "בדקי אם חדר 4 פנוי ביום רביעי 02.12.2026, וכתבי את שעות הזמינות שלו."
AVAILABILITY_ARGS = {"room_id": 4, "date": "2026-12-02"}


def build_trace(*, inject_temporary_failure: bool) -> dict:
    """Run a complete model-decision -> tool -> observation -> final-answer loop."""
    backend = MockBackend()
    tools = CampusTools(backend, retries=2)
    answer = (
        "לא ניתן לבדוק זמינות כרגע: שירות החדרים אינו זמין זמנית. לא בוצע שינוי."
        if inject_temporary_failure else
        "חדר 4 פנוי ביום 02.12.2026 בין 08:00–10:00 ובין 12:00–22:00."
    )
    # Exactly three temporary failures exhaust retries (initial call + two retries).
    backend.fail_next = 3 if inject_temporary_failure else 0
    authored_actions = [
        {"tool": "get_availability", "arguments": deepcopy(AVAILABILITY_ARGS)},
        {"message": answer},
    ]
    model = ScriptedModel(authored_actions)
    agent = CampusAgent(model, tools, context_mode="full", max_steps=4)
    count_before = len(backend.reservations)
    final = agent.chat("milestone1-archive", REQUEST)
    count_after = len(backend.reservations)
    session = agent.session("milestone1-archive")

    observations = [json.loads(msg["content"]) for msg in session.messages
                    if msg["role"] == "tool"]
    if len(tools.trace) != 1 or len(observations) != 1 or len(session.audit) != 2:
        raise AssertionError("Unexpected trace length; inspect the agent loop")
    if final != {"status": "ok", "answer": answer}:
        raise AssertionError("Scripted final response was not produced")
    if count_before != 6 or count_after != 6:
        raise AssertionError("Read-only demo unexpectedly modified bookings")
    if inject_temporary_failure:
        if (tools.trace[0]["status"] != "error" or
                tools.trace[0].get("reason") != "service_unavailable" or
                tools.trace[0]["attempts"] != 3 or
                observations[0]["error"]["retryable"] is not True):
            raise AssertionError("Temporary-failure path did not exhaust retry budget")
    elif (tools.trace[0]["status"] != "ok" or
          tools.trace[0]["attempts"] != 1 or
          observations[0]["data"]["free_windows"] != [
              {"start": "08:00", "end": "10:00"},
              {"start": "12:00", "end": "22:00"},
          ]):
        raise AssertionError("Successful path did not produce expected availability")

    scenario = "transient_failure" if inject_temporary_failure else "success"
    trace = {
        "scenario": scenario,
        "simulation_notice": (
            "This is a REPRODUCIBLE SCRIPTED MOCK run, NOT a real LLM decision. "
            "No SQL Server, API, GPU, or private database was used."
        ),
        "setup": {
            "decision_provider": "ScriptedModel (predetermined decisions)",
            "data_provider": "MockBackend (120 synthetic rooms, 6 synthetic reservations)",
            "context_mode": "full",
            "agent_step_limit": 4,
            "read_retries": 2,
            "temporary_failures_injected": 3 if inject_temporary_failure else 0,
        },
        "user_request": REQUEST,
        "scripted_decisions": deepcopy(authored_actions),
        "timeline": [
            {
                "step": 1,
                "actor": "ScriptedModel",
                "decision": "call_tool",
                "tool": "get_availability",
                "arguments": deepcopy(AVAILABILITY_ARGS),
            },
            {
                "step": 1,
                "actor": "CampusTools",
                "decision": "execute_and_observe",
                "tool": "get_availability",
                "attempts": tools.trace[0]["attempts"],
                "observation": observations[0],
            },
            {
                "step": 2,
                "actor": "ScriptedModel",
                "decision": "final_answer",
                "answer": answer,
                "stop_reason": "model_returned_message",
            },
        ],
        "tool_trace": deepcopy(tools.trace),
        "agent_audit": deepcopy(session.audit),
        "backend_calls": backend.calls,
        "reservations_before": count_before,
        "reservations_after": count_after,
        "final_result": final,
        "assessment": {
            "tool_outcome": tools.trace[0]["status"],
            "temporary_error_detected": inject_temporary_failure,
            "error_class": "service_unavailable" if inject_temporary_failure else None,
            "read_only_unchanged": count_before == count_after,
            "did_model_understand_hebrew": "Not tested: answers/decisions were scripted",
        },
    }
    return trace


def write_traces(output_dir: Path = TRACE_DIRECTORY) -> dict[str, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    generated = {}
    for scenario, injected in (("success", False), ("transient_failure", True)):
        content = build_trace(inject_temporary_failure=injected)
        filename = output_dir / f"{scenario}.json"
        filename.write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        generated[scenario] = filename
    return generated


def main() -> None:
    generated = write_traces()
    for name, path in generated.items():
        data = json.loads(path.read_text(encoding="utf-8"))
        tool = data["tool_trace"][0]
        print(f"{name}: {path.relative_to(ROOT).as_posix()} | "
              f"tool={tool['tool']} | status={tool['status']} | attempts={tool['attempts']} | "
              f"reservations={data['reservations_before']}->{data['reservations_after']}")
        if name == "transient_failure":
            print("  reason=service_unavailable; retryable=True; no booking changed")
    print("NOTE: Both traces come from ScriptedModel + MockBackend, NOT from a live LLM or SQL Server.")


if __name__ == "__main__":
    main()
