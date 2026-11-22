"""No DB/network calls. Each implemented tool: valid, invalid, transient."""
from src.mock_backend import MockBackend
from src.tools import CampusTools


DAY = "2026-12-02"  # Wednesday


def find_args(**updates):
    data = {"date": DAY, "min_capacity": 40, "min_computers": 20,
            "require_projector": True, "start_time": "10:00", "end_time": "12:00"}
    data.update(updates)
    return data


def test_find_valid_and_sorted():
    result = CampusTools(MockBackend()).run("find_rooms", find_args())
    assert result["status"] == "ok"
    rooms = result["data"]["rooms"]
    assert rooms and len(rooms) <= 5
    assert all(r["Capacity"] >= 40 and r["ComputerCount"] >= 20 and r["HasProjector"] for r in rooms)
    assert [r["Capacity"] for r in rooms] == sorted(r["Capacity"] for r in rooms)
    assert all(r["RoomID"] != 4 for r in rooms)  # room 4 busy during 10:00-12:00


def test_find_invalid_rejected_without_execution():
    mock = MockBackend()
    tools = CampusTools(mock)
    result = tools.run("find_rooms", find_args(min_capacity=-50))
    assert result["error"]["type"] == "invalid_input"
    assert mock.calls == 0 and tools.trace[0]["attempts"] == 0


def test_find_transient_retry():
    mock = MockBackend()
    mock.fail_next = 2
    tools = CampusTools(mock)
    result = tools.run("find_rooms", find_args())
    assert result["status"] == "ok"
    assert tools.trace[0]["attempts"] == 3


def test_availability_valid():
    result = CampusTools(MockBackend()).run("get_availability", {"room_id": 4, "date": DAY})
    assert result["status"] == "ok"
    assert result["data"]["free_windows"] == [
        {"start": "08:00", "end": "10:00"},
        {"start": "12:00", "end": "22:00"}
    ]


def test_availability_invalid():
    mock = MockBackend()
    result = CampusTools(mock).run("get_availability", {"room_id": -1, "date": DAY})
    assert result["error"]["type"] == "invalid_input"
    assert mock.calls == 0


def test_availability_transient_retry():
    mock = MockBackend()
    mock.fail_next = 1
    tools = CampusTools(mock)
    result = tools.run("get_availability", {"room_id": 4, "date": DAY})
    assert result["status"] == "ok"
    assert tools.trace[0]["attempts"] == 2


def test_weekend_rejected():
    tools = CampusTools(MockBackend())
    result = tools.run("find_rooms", find_args(date="2026-12-05"))
    assert result["error"]["type"] == "invalid_input"


def test_missing_hours_returns_free_windows():
    args = find_args()
    del args["start_time"]
    del args["end_time"]
    result = CampusTools(MockBackend()).run("find_rooms", args)
    assert result["status"] == "ok"
    assert all(room["available_slots"] for room in result["data"]["rooms"])


def test_permanent_room_not_found_is_not_retried():
    tools = CampusTools(MockBackend())
    result = tools.run("get_availability", {"room_id": 999, "date": DAY})
    assert result["error"]["type"] == "room_not_found"
    assert tools.trace[0]["attempts"] == 1


def test_retry_budget_exhaustion():
    mock = MockBackend()
    mock.fail_next = 10
    tools = CampusTools(mock, retries=2)
    result = tools.run("find_rooms", find_args())
    assert result["error"]["type"] == "service_unavailable"
    assert result["error"]["retryable"] is True
    assert tools.trace[0]["attempts"] == 3
