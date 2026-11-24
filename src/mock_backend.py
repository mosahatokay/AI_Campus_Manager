"""In-memory *synthetic* campus for repeatable Colab demos; not the user's SQL data."""
from __future__ import annotations
from datetime import datetime, timedelta
from threading import Lock


class TransientBackendError(RuntimeError):
    """Simulated recoverable backend error for deterministic test cases."""


class MockBackend:
    def __init__(self):
        self.rooms = []
        self.reservations = []
        self.fail_next = 0
        self.calls = 0
        self._reservation_lock = Lock()
        room_id = 0
        for building in range(1, 6):
            for floor in range(1, 4):
                for number, capacity in enumerate((20, 25, 30, 40, 45, 50, 55, 60), 1):
                    room_id += 1
                    self.rooms.append({
                        "RoomID": room_id, "BuildingID": building,
                        "FloorNumber": floor, "RoomNumber": number,
                        "Capacity": capacity,
                        "ComputerCount": (0, 0, 10, 20, 0, 30, 40, 60)[number - 1],
                        "HasProjector": number % 2 == 0,
                    })
        # Six artificial reservations on a Wednesday. Deliberately not real campus bookings.
        day = "2026-12-02"
        for idx, (room, start, end) in enumerate((
            (1, "08:00", "10:00"), (4, "10:00", "12:00"),
            (8, "12:00", "14:00"), (12, "14:00", "16:00"),
            (20, "16:00", "18:00"), (25, "18:00", "20:00"),
        ), 1):
            self.reservations.append({
                "ReservationID": idx, "RoomID": room,
                "StartTime": datetime.fromisoformat(f"{day}T{start}"),
                "EndTime": datetime.fromisoformat(f"{day}T{end}"),
                "Title": f"Synthetic event {idx}",
                "EventName": f"Synthetic event {idx}",
                "EventType": "Event",
                "StudentCount": 20,
            })

    def maybe_fail(self):
        self.calls += 1
        if self.fail_next > 0:
            self.fail_next -= 1
            raise TransientBackendError("Simulated temporary database outage")

    def list_rooms(self):
        self.maybe_fail()
        return list(self.rooms)

    def room_by_id(self, room_id):
        self.maybe_fail()
        return next((x for x in self.rooms if x["RoomID"] == room_id), None)

    def busy_ranges(self, room_id, day):
        self.maybe_fail()
        return [
            (r["StartTime"], r["EndTime"])
            for r in self.reservations
            if r["RoomID"] == room_id and
            r["StartTime"] < day + timedelta(days=1) and
            r["EndTime"] > day
        ]

    def list_exams(self, *, day, building_id=None, room_id=None, start=None, end=None):
        """List synthetic exams using the same overlap rules as SQL Server."""
        self.maybe_fail()
        day_end = day + timedelta(days=1)
        by_id = {room["RoomID"]: room for room in self.rooms}
        with self._reservation_lock:
            matches = []
            for reservation in self.reservations:
                if reservation["EventType"] != "Exam":
                    continue
                if not (reservation["StartTime"] < day_end and reservation["EndTime"] > day):
                    continue
                room = by_id.get(reservation["RoomID"])
                if room is None:
                    continue
                if building_id is not None and room["BuildingID"] != building_id:
                    continue
                if room_id is not None and room["RoomID"] != room_id:
                    continue
                if start is not None and not (
                    reservation["StartTime"] < end and reservation["EndTime"] > start
                ):
                    continue
                matches.append({**reservation,
                                "BuildingID": room["BuildingID"],
                                "FloorNumber": room["FloorNumber"],
                                "RoomNumber": room["RoomNumber"]})
        return matches

    def create_reservation_atomic(self, *, room_id, event_name, event_type, start, end,
                                  student_count, min_computers=0, require_projector=False):
        """Atomically recheck room constraints/conflicts and add one mock booking."""
        self.maybe_fail()
        with self._reservation_lock:
            room = next((r for r in self.rooms if r["RoomID"] == room_id), None)
            if room is None or room["Capacity"] < student_count:
                return None
            if room["ComputerCount"] < min_computers:
                return None
            if require_projector and not room["HasProjector"]:
                return None
            if any(r["RoomID"] == room_id and r["StartTime"] < end and
                   r["EndTime"] > start for r in self.reservations):
                return None
            reservation_id = max((r["ReservationID"] for r in self.reservations), default=0) + 1
            self.reservations.append({
                "ReservationID": reservation_id, "RoomID": room_id,
                "EventName": event_name, "EventType": event_type,
                "StartTime": start, "EndTime": end,
                "StudentCount": student_count,
            })
            return reservation_id

    def cancel_reservation_atomic(self, reservation_id):
        """Remove exactly one synthetic reservation under the booking lock."""
        self.maybe_fail()
        with self._reservation_lock:
            for idx, row in enumerate(self.reservations):
                if row["ReservationID"] == reservation_id:
                    return self.reservations.pop(idx)
            return None

    def reservation_by_id(self, reservation_id):
        """Return a snapshot to support compare-and-update semantics."""
        self.maybe_fail()
        with self._reservation_lock:
            row = next((r for r in self.reservations if r["ReservationID"] == reservation_id), None)
            return dict(row) if row is not None else None

    def update_reservation_atomic(self, *, reservation_id, expected, room_id,
                                  event_name, event_type, start, end, student_count,
                                  min_computers=0, require_projector=False):
        """Update in place under the booking lock, rechecking original state and conflicts."""
        self.maybe_fail()
        with self._reservation_lock:
            booking = next((r for r in self.reservations if r["ReservationID"] == reservation_id), None)
            if booking is None or any(
                booking[k] != expected[k] for k in
                ("RoomID", "EventName", "EventType", "StartTime", "EndTime", "StudentCount")
            ):
                return None
            room = next((r for r in self.rooms if r["RoomID"] == room_id), None)
            if (room is None or room["Capacity"] < student_count or
                room["ComputerCount"] < min_computers or
                (require_projector and not room["HasProjector"])):
                return None
            if any(
                r["ReservationID"] != reservation_id and r["RoomID"] == room_id and
                r["StartTime"] < end and r["EndTime"] > start
                for r in self.reservations
            ):
                return None
            booking.update(RoomID=room_id, EventName=event_name, EventType=event_type,
                           StartTime=start, EndTime=end, StudentCount=student_count)
            return dict(booking)
