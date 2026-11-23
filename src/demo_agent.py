"""Run a zero-cost deterministic (NOT real LLM) CampusAI agent demo.

python -m src.demo_agent
"""
from __future__ import annotations
import json
from .agent import CampusAgent
from .agent_models import ScriptedModel
from .mock_backend import MockBackend
from .tools import CampusTools


def display(label, payload):
    print("\n=== " + label + " ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main():
    backend = MockBackend()
    tools = CampusTools(backend)
    model = ScriptedModel([
        {"tool": "find_rooms", "arguments": {
            "date": "2026-12-02", "min_capacity": 40,
            "min_computers": 20, "require_projector": True,
            "start_time": "10:00", "end_time": "12:00",
        }},
        {"message": "מצאתי חדרים מתאימים למבחן. אין הזמנה חדשה בשלב זה."},
        {"tool": "create_reservation", "arguments": {
            "room_id": 12, "event_name": "Demo Exam", "event_type": "Exam",
            "date": "2026-12-02", "start_time": "12:00", "end_time": "14:00",
            "student_count": 35, "min_computers": 20, "require_projector": True,
        }},
    ])
    agent = CampusAgent(model, tools, context_mode="compact")
    display("1. Search (model-test-double proposes tool; tool executes)",
            agent.chat("secretary", "מצאי לי חדר למבחן ל-35 סטודנטים עם 20 מחשבים ומקרן ברביעי 2.12 בשעה 10 עד 12"))
    display("2. Proposal only; bookings are unchanged",
            agent.chat("secretary", "בבקשה הזמיני חדר 12 מ-12 עד 14"))
    display("Bookings BEFORE approval", {"count": len(backend.reservations)})
    display("3. Explicit application approval", agent.confirm("secretary", approved=True))
    display("Bookings AFTER approval", {"count": len(backend.reservations)})
    display("Tool execution trace", tools.trace)
    display("Agent audit trail", agent.session("secretary").audit)
    print("\nIMPORTANT: ScriptedModel simulates decisions. It is NOT an LLM. No API, SQL or money used.")


if __name__ == "__main__":
    main()
