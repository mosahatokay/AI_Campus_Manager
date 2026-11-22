"""In-memory *synthetic* campus for repeatable Colab demos; not the user's SQL data."""
from __future__ import annotations
from datetime import datetime, timedelta


class TransientBackendError(RuntimeError):
    """Simulated recoverable backend error for deterministic test cases."""


class MockBackend:
    def __init__(self):
        self.rooms = []
        self.reservations = []
        self.fail_next = 0
        self.calls = 0
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
