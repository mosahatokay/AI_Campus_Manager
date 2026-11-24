"""Reproducible FULL-vs-COMPACT context retention comparison (NO LLM/API).

Usage: python -m src.context_comparison
Writes docs/context_comparison_results.json and prints the comparison.
Only synthetic MockBackend reservations are used; SQL Server is never connected.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from .agent import CampusAgent
from .agent_models import ScriptedModel
from .mock_backend import MockBackend
from .tools import CampusTools

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "docs" / "context_comparison_results.json"
QUESTION = "מה שם האירוע של ההזמנה שאושרה קודם?"
EVENT_NAME = "Physics Midterm - Synthetic Test"

# A fixed TEST FIXTURE deliberately places the title in the approved write result.
# This does not simulate natural-language comprehension or autonomous decisions.
CREATE_ARGS = {
    "room_id": 12,
    "event_name": EVENT_NAME,
    "event_type": "Exam",
    "date": "2026-12-03",  # Thursday, with no synthetic reservation in this room.
    "start_time": "13:00",
    "end_time": "14:00",
    "student_count": 35,
    "min_computers": 20,
    "require_projector": True,
}


class VerifiedResultReader:
    """Deterministic context reader, *not a language model*.

    It answers only if an explicitly verified tool result containing the event
    name remains in the messages supplied to it. It does not read the backend,
    and does not guess an absent title.
    """

    def __init__(self):
        self.received_context = None

    def choose(self, messages, tools):
        self.received_context = deepcopy(messages)
        prefix = "Application-verified reservation action result: "
        for message in reversed(messages):
            content = message.get("content")
            if message.get("role") != "assistant" or not isinstance(content, str):
                continue
            if not content.startswith(prefix):
                continue
            try:
                observed = json.loads(content[len(prefix):])
            except json.JSONDecodeError:
                continue
            if observed.get("status") != "ok":
                continue
            name = observed.get("data", {}).get("event_name")
            if isinstance(name, str) and name:
                return {"message": name}
        return {"message": "אין לי את שם האירוע בהקשר שנמסר לי."}


def run_comparison(*, save=True):
    rows = []
    for mode in ("full", "compact"):
        backend = MockBackend()
        agent = CampusAgent(
            ScriptedModel([{"tool": "create_reservation", "arguments": deepcopy(CREATE_ARGS)}]),
            CampusTools(backend), context_mode=mode
        )
        proposal = agent.chat("secretary", "בצעי את הזמנת הדוגמה שהוכנה לצורך ניסוי הזיכרון.")
        assert proposal["status"] == "awaiting_confirmation"
        assert len(backend.reservations) == 6
        confirmed = agent.confirm("secretary", approved=True)
        assert confirmed["status"] == "ok"
        assert len(backend.reservations) == 7
        assert any(r.get("EventName") == EVENT_NAME for r in backend.reservations)

        # The exact same 8 synthetic follow-up turns happen in both modes.
        # Full mode retains them all; compact keeps only the last few turns.
        for number in range(1, 9):
            agent.model = ScriptedModel([{"message": "קיבלתי, תודה."}])
            reply = agent.chat("secretary", f"רישום מעקב כללי מספר {number}, ללא פרטי ההזמנה.")
            assert reply["status"] == "ok"

        model = VerifiedResultReader()
        agent.model = model
        result = agent.chat("secretary", QUESTION)
        assert result["status"] == "ok"
        transmitted = model.received_context
        assert isinstance(transmitted, list)
        serialized = json.dumps(transmitted, ensure_ascii=False, separators=(",", ":"))
        rows.append({
            "mode": mode,
            "messages": len(transmitted),
            "characters": len(serialized),
            "question": QUESTION,
            "answer": result["answer"],
            "expected": EVENT_NAME,
            "answer_correct": result["answer"] == EVENT_NAME,
            "notes": (
                "The approved event title survives in the full verified result."
                if mode == "full" else
                "The structured compact summary omits the event title; the reader does not guess."
            ),
        })

    assert rows[0]["answer_correct"] is True
    assert rows[1]["answer_correct"] is False
    assert rows[0]["characters"] > rows[1]["characters"]
    result = {
        "experiment": "Identical approved reservation + 8 follow-up turns + same factual question",
        "model": "VerifiedResultReader (rule-based test double, NOT an LLM)",
        "data": "Synthetic MockBackend; no SQL Server/API/paid inference",
        "claim_limit": "Tests which facts remain in context. Does not measure LLM accuracy.",
        "results": rows,
    }
    if save:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


def main():
    result = run_comparison(save=True)
    print("\n=== Context comparison (synthetic fixture, not an LLM) ===")
    for row in result["results"]:
        verdict = "correct" if row["answer_correct"] else "missing information"
        print(f"{row['mode']}: {row['messages']} messages, "
              f"{row['characters']} chars, answer={row['answer']!r}, {verdict}")
    print("Question:", QUESTION)
    print("Expected answer:", EVENT_NAME)
    print("Lost in compact context: approved event name; room/date/time metadata remain.")
    print("Saved:", REPORT.relative_to(ROOT).as_posix())
    print("NOTE: This is a deterministic mock context-retention experiment, NOT an LLM benchmark.")


if __name__ == "__main__":
    main()
