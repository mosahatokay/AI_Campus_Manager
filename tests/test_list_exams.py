"""list_exams: independent, offline-only tests; SQL mode never connects here."""
from datetime import datetime
from jsonschema import Draft202012Validator, FormatChecker
import pytest

from src.agent import safe_memory, tool_definitions, CampusAgent
from src.agent_models import ScriptedModel
from src.mock_backend import MockBackend
from src.sql_backend import SQLServerBackend
from src.tools import CampusTools, CONTRACTS

DAY = "2026-12-02"


def make_backend():
    backend = MockBackend()
    specs = [
        (4, "Physics exam", "2026-12-02T12:00", "2026-12-02T13:30", 30),
        (12, "History exam", "2026-12-02T09:00", "2026-12-02T10:00", 30),
        (25, "Math exam", "2026-12-02T14:00", "2026-12-02T15:00", 20),
        (8, "Chemistry exam", "2026-12-02T14:00", "2026-12-02T15:00", 40),
        (5, "Programming class", "2026-12-02T09:00", "2026-12-02T10:00", 20),
    ]
    for room_id, title, start, end, students in specs:
        kind = "Class" if "class" in title.lower() else "Exam"
        identifier = backend.create_reservation_atomic(
            room_id=room_id, event_name=title, event_type=kind,
            start=datetime.fromisoformat(start), end=datetime.fromisoformat(end),
            student_count=students,
        )
        assert identifier is not None
    backend.calls = 0
    return backend


def test_contract_schema_and_no_approval():
    contract = CONTRACTS["list_exams"]
    Draft202012Validator.check_schema(contract["input_schema"])
    Draft202012Validator.check_schema(contract["output_schema"])
    assert contract["permissions"]["read_only"] is True
    assert contract["requires_approval"] is False


def test_valid_list_exams_includes_exam_fields_not_class_or_events():
    backend = make_backend()
    before = len(backend.reservations)
    result = CampusTools(backend).run("list_exams", {"date": DAY})
    assert result["status"] == "ok"
    names = [r["event_name"] for r in result["data"]["exams"]]
    assert names == ["History exam", "Physics exam", "Chemistry exam", "Math exam"]
    assert len(backend.reservations) == before
    assert result["data"]["exams"][0]["room_id"] == 12
    assert result["data"]["exams"][0]["start_time"] == "09:00"
    assert result["data"]["exams"][0]["date"] == DAY
    assert not list(Draft202012Validator(
        CONTRACTS["list_exams"]["output_schema"], format_checker=FormatChecker()
    ).iter_errors(result))


def test_no_matching_exams_returns_successful_empty_list():
    result = CampusTools(MockBackend()).run("list_exams", {"date": DAY})
    assert result == {"status": "ok", "data": {"date": DAY, "exams": []}}


def test_filter_by_building_and_room_and_overlapping_time():
    tools = CampusTools(make_backend())
    result = tools.run("list_exams", {"date": DAY, "building_id": 1, "room_id": 4,
                                       "start_time": "13:00", "end_time": "14:00"})
    assert [x["event_name"] for x in result["data"]["exams"]] == ["Physics exam"]
    # Boundary: Physics starts at 12:00, so a window ending exactly at 12:00 is NOT overlap.
    result = tools.run("list_exams", {"date": DAY, "room_id": 4,
                                       "start_time": "10:00", "end_time": "12:00"})
    assert result["data"]["exams"] == []
    result = tools.run("list_exams", {"date": DAY, "building_id": 2})
    assert [x["event_name"] for x in result["data"]["exams"]] == ["Math exam"]
    result = tools.run("list_exams", {"date": DAY, "building_id": 2, "room_id": 4})
    assert result["data"]["exams"] == []


def test_building_filter_does_not_disclose_events_in_other_buildings():
    names = [e["event_name"] for e in CampusTools(make_backend()).run(
        "list_exams", {"date": DAY, "building_id": 1})["data"]["exams"]]
    assert "Math exam" not in names
    assert len(names) == 3


@pytest.mark.parametrize("arguments", [
    {}, {"date": "2026-02-30"}, {"date": DAY, "room_id": -1},
    {"date": DAY, "building_id": 0}, {"date": DAY, "start_time": "09:00"},
    {"date": DAY, "end_time": "10:00"},
    {"date": DAY, "start_time": "15:00", "end_time": "14:00"},
    {"date": DAY, "start_time": "07:59", "end_time": "09:00"},
    {"date": DAY, "start_time": "21:00", "end_time": "22:01"},
    {"date": DAY, "start_time": "12:00", "end_time": "12:00"},
    {"date": "2026-12-05"}, {"date": DAY, "approved": True},
    {"date": DAY, "building_id": "1; DROP TABLE Reservations;"},
])
def test_invalid_inputs_make_zero_backend_calls(arguments):
    backend = MockBackend()
    result = CampusTools(backend).run("list_exams", arguments)
    assert result["status"] == "error"
    assert result["error"]["type"] == "invalid_input"
    assert backend.calls == 0


def test_read_retry_recovers_from_temporary_failure():
    backend = make_backend()
    backend.fail_next = 1
    tools = CampusTools(backend, retries=2)
    result = tools.run("list_exams", {"date": DAY})
    assert result["status"] == "ok"
    assert tools.trace[-1]["attempts"] == 2
    assert backend.calls == 2


def test_retry_limit_reports_temporary_error_without_writes():
    backend = make_backend()
    before = [dict(r) for r in backend.reservations]
    backend.fail_next = 3
    tools = CampusTools(backend, retries=2)
    result = tools.run("list_exams", {"date": DAY})
    assert result["status"] == "error"
    assert result["error"]["type"] == "service_unavailable"
    assert result["error"]["retryable"] is True
    assert tools.trace[-1]["attempts"] == 3
    assert backend.reservations == before


def test_model_tool_registry_and_scripted_agent_flow():
    definitions = tool_definitions()
    assert any(x["function"]["name"] == "list_exams" for x in definitions)
    backend = make_backend()
    agent = CampusAgent(ScriptedModel([
        {"tool": "list_exams", "arguments": {"date": DAY}},
        {"message": "מצאתי ארבעה מבחנים."},
    ]), CampusTools(backend))
    result = agent.chat("secretary", "אילו מבחנים יש ביום רביעי 2.12.2026?")
    assert result == {"status": "ok", "answer": "מצאתי ארבעה מבחנים."}
    assert agent.tools.trace[0]["tool"] == "list_exams"
    assert agent.tools.trace[0]["status"] == "ok"


def test_safe_memory_excludes_untrusted_event_titles():
    raw = CampusTools(make_backend()).run("list_exams", {"date": DAY})
    memory = safe_memory("list_exams", raw)
    assert len(memory["exams"]) == 4
    assert "Physics exam" not in str(memory)
    assert memory["exams"][0]["reservation_id"] >= 1


def test_sql_backend_uses_parameterized_query_without_real_connection():
    captured = []

    class Cursor:
        description = [(key,) for key in (
            "ReservationID", "RoomID", "BuildingID", "FloorNumber", "RoomNumber",
            "EventName", "StartTime", "EndTime", "StudentCount")]
        def fetchall(self):
            return [(11, 4, 1, 1, 4, "Exam", datetime(2026,12,2,12), datetime(2026,12,2,13), 30)]

    backend = SQLServerBackend.__new__(SQLServerBackend)
    backend.query = lambda statement, *args: (captured.append((statement, args)) or Cursor())
    rows = backend.list_exams(day=datetime.fromisoformat(DAY), building_id=1, room_id=4,
                              start=datetime.fromisoformat(DAY + "T12:00"),
                              end=datetime.fromisoformat(DAY + "T14:00"))
    assert len(rows) == 1 and rows[0]["RoomID"] == 4
    statement, params = captured[0]
    assert "res.EventType = 'Exam'" in statement
    assert statement.count("?") == len(params) == 6
    assert params[2] == 1 and params[3] == 4
    assert "12:00" not in statement
