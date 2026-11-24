"""Read-only CampusAI exams demo on synthetic in-memory data.

python -m src.demo_exams
"""
from datetime import datetime
import json
from .mock_backend import MockBackend
from .tools import CampusTools


def main():
    backend = MockBackend()
    identifier = backend.create_reservation_atomic(
        room_id=4, event_name="Synthetic Physics Exam", event_type="Exam",
        start=datetime.fromisoformat("2026-12-02T12:00"),
        end=datetime.fromisoformat("2026-12-02T14:00"), student_count=30,
    )
    assert identifier is not None
    count_before = len(backend.reservations)
    result = CampusTools(backend).run("list_exams", {
        "date": "2026-12-02", "building_id": 1,
        "start_time": "12:00", "end_time": "15:00",
    })
    assert result["status"] == "ok"
    assert len(result["data"]["exams"]) == 1
    assert len(backend.reservations) == count_before
    print("=== list_exams: simulated EXAM only (not real college data) ===")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"Reservations before/after READ: {count_before}/{len(backend.reservations)}")
    print("No real LLM, SQL Server, API, or paid service used.")


if __name__ == "__main__":
    main()
