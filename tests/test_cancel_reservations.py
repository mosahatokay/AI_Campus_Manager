"""Offline cancellation tests; no SQL Server instance is touched."""
from datetime import datetime
import pytest
from src.mock_backend import MockBackend
from src.tools import CampusTools


def test_cancel_requires_human_approval_and_makes_zero_calls():
    backend = MockBackend()
    result = CampusTools(backend).run("cancel_reservation", {"reservation_id": 4})
    assert result["error"]["type"] == "approval_required"
    assert backend.calls == 0 and len(backend.reservations) == 6


@pytest.mark.parametrize("bad_args", [
    {"reservation_id": 0}, {"reservation_id": -1},
    {"reservation_id": "4"}, {"reservation_id": 4, "approved": True},
    {},
])
def test_cancel_bad_input_rejected(bad_args):
    backend = MockBackend()
    result = CampusTools(backend).run("cancel_reservation", bad_args, approved=True)
    assert result["error"]["type"] == "invalid_input"
    assert backend.calls == 0 and len(backend.reservations) == 6


def test_cancel_success_releases_slot_and_keeps_other_reservations():
    backend = MockBackend()
    tools = CampusTools(backend)
    before = tools.run("get_availability", {"room_id": 4, "date": "2026-12-02"})
    assert before["data"]["free_windows"] == [
        {"start": "08:00", "end": "10:00"}, {"start": "12:00", "end": "22:00"}
    ]
    result = tools.run("cancel_reservation", {"reservation_id": 2}, approved=True)
    assert result == {"status": "ok", "data": {
        "reservation_id": 2, "room_id": 4, "date": "2026-12-02",
        "start_time": "10:00", "end_time": "12:00"}}
    assert len(backend.reservations) == 5
    assert {r["ReservationID"] for r in backend.reservations} == {1, 3, 4, 5, 6}
    after = tools.run("get_availability", {"room_id": 4, "date": "2026-12-02"})
    assert after["data"]["free_windows"] == [{"start": "08:00", "end": "22:00"}]


def test_cancel_twice_is_not_repeatable():
    tools = CampusTools(MockBackend())
    assert tools.run("cancel_reservation", {"reservation_id": 2}, approved=True)["status"] == "ok"
    result = tools.run("cancel_reservation", {"reservation_id": 2}, approved=True)
    assert result["error"]["type"] == "reservation_not_found"
    assert tools.trace[-1]["attempts"] == 1


def test_cancel_unknown_id_does_not_change_anything():
    backend = MockBackend()
    result = CampusTools(backend).run("cancel_reservation", {"reservation_id": 999}, approved=True)
    assert result["error"]["type"] == "reservation_not_found"
    assert len(backend.reservations) == 6


def test_cancel_transient_error_has_no_automatic_retry():
    backend = MockBackend()
    backend.fail_next = 1
    tools = CampusTools(backend, retries=5)
    result = tools.run("cancel_reservation", {"reservation_id": 2}, approved=True)
    assert result["error"]["type"] == "write_outcome_unknown"
    assert result["error"]["retryable"] is False
    assert len(backend.reservations) == 6
    assert backend.calls == 1 and tools.trace[-1]["attempts"] == 1


def test_cancel_newly_created_reservation():
    backend = MockBackend()
    tools = CampusTools(backend)
    create = tools.run("create_reservation", {
        "room_id": 4, "event_name": "A", "event_type": "Exam",
        "date": "2026-12-02", "start_time": "12:00", "end_time": "14:00",
        "student_count": 30,
    }, approved=True)
    assert create["status"] == "ok"
    new_id = create["data"]["reservation_id"]
    cancel = tools.run("cancel_reservation", {"reservation_id": new_id}, approved=True)
    assert cancel["status"] == "ok" and cancel["data"]["reservation_id"] == new_id
    assert new_id not in {r["ReservationID"] for r in backend.reservations}


def test_cancel_has_trace_for_rejected_and_successful_actions():
    tools = CampusTools(MockBackend())
    tools.run("cancel_reservation", {"reservation_id": 3})
    tools.run("cancel_reservation", {"reservation_id": 3}, approved=True)
    assert [x["decision"] for x in tools.trace] == ["rejected", "executed"]
    assert [x["attempts"] for x in tools.trace] == [0, 1]
