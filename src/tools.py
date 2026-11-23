"""Validated campus tools for SQL Server / synthetic mock backends."""
from __future__ import annotations
from datetime import date, datetime
import json
from pathlib import Path
import time
from jsonschema import Draft202012Validator, FormatChecker
from .mock_backend import TransientBackendError

ROOT = Path(__file__).resolve().parent.parent
CONTRACTS = {
    "find_rooms": json.loads((ROOT / "tool_contract.json").read_text(encoding="utf-8")),
    "get_availability": json.loads((ROOT / "availability_contract.json").read_text(encoding="utf-8")),
    "create_reservation": json.loads((ROOT / "reservation_contract.json").read_text(encoding="utf-8")),
    "cancel_reservation": json.loads((ROOT / "cancel_contract.json").read_text(encoding="utf-8")),
    "update_reservation": json.loads((ROOT / "update_contract.json").read_text(encoding="utf-8")),
}
WORKING_DAYS = {6, 0, 1, 2, 3}  # Sun–Thu (datetime.weekday: Mon=0, Sun=6)
OPEN, CLOSE = "08:00", "22:00"


def ok(data):
    return {"status": "ok", "data": data}


def err(kind, message, retryable=False):
    return {"status": "error", "error": {
        "type": kind, "message": str(message), "retryable": bool(retryable)
    }}


def windows(busy, day):
    """Free periods inside 08:00–22:00, merging overlapping busy ranges."""
    start = datetime.fromisoformat(f"{day}T{OPEN}")
    finish = datetime.fromisoformat(f"{day}T{CLOSE}")
    ranges = sorted((max(start, a), min(finish, b)) for a, b in busy if b > start and a < finish)
    free = []
    current = start
    for a, b in ranges:
        if a > current:
            free.append({"start": current.strftime("%H:%M"), "end": a.strftime("%H:%M")})
        current = max(current, b)
    if current < finish:
        free.append({"start": current.strftime("%H:%M"), "end": finish.strftime("%H:%M")})
    return free


def includes(free, start, end):
    return any(slot["start"] <= start and end <= slot["end"] for slot in free)


class CampusTools:
    def __init__(self, backend, retries=2, sleep=lambda _: None):
        self.backend = backend
        self.retries = retries
        self.sleep = sleep
        self.trace = []

    def run(self, name, args, *, approved=False):
        """Approval is supplied by trusted application code, never tool/model args.

        The user-facing application must verify a real secretary confirmation
        before passing approved=True for a write operation.
        """
        began = time.perf_counter()
        event = {"tool": name, "decision": "rejected", "attempts": 0}
        if name not in CONTRACTS:
            result = err("invalid_input", "Unknown tool")
        elif not isinstance(args, dict):
            result = err("invalid_input", "Tool arguments must be an object")
        else:
            validator = Draft202012Validator(CONTRACTS[name]["input_schema"], format_checker=FormatChecker())
            issue = next(validator.iter_errors(args), None)
            if issue is not None:
                result = err("invalid_input", issue.message)
            elif name in {"create_reservation", "cancel_reservation", "update_reservation"} and not approved:
                result = err("approval_required", "Secretary confirmation required before saving")
            else:
                result = self._validated_run(name, args, event)
        event["status"] = result["status"]
        if result["status"] == "error":
            event["reason"] = result["error"]["type"]
        event["latency_ms"] = round((time.perf_counter() - began) * 1000, 2)
        self.trace.append(event)
        return result

    def _validated_run(self, name, args, event):
        # A cancellation has only a reservation_id, not a date.
        if name in {"cancel_reservation", "update_reservation"}:
            return self._validated_write(name, args, event)
        day = date.fromisoformat(args["date"])
        if day.weekday() not in WORKING_DAYS:
            return err("invalid_input", "College is closed on Friday and Saturday")
        if name in {"find_rooms", "create_reservation"}:
            start, end = args.get("start_time"), args.get("end_time")
            if start is not None and (start < OPEN or end > CLOSE or start >= end):
                return err("invalid_input", "Time must be increasing and within 08:00–22:00")

        if name == "create_reservation":
            return self._validated_write(name, args, event)

        for attempt in range(1, self.retries + 2):
            event["attempts"] = attempt
            event["decision"] = "executed"
            try:
                if name == "find_rooms":
                    result = self._find_rooms(args)
                else:
                    result = self._get_availability(args)
                schema_issue = next(Draft202012Validator(
                    CONTRACTS[name]["output_schema"], format_checker=FormatChecker()
                ).iter_errors(result), None)
                if schema_issue is not None:
                    return err("database_error" if name == "get_availability" else "invalid_output",
                               "Tool returned data violating output contract")
                return result
            except TransientBackendError:
                if attempt > self.retries:
                    return err("service_unavailable", "Temporary backend failure; retries exhausted", True)
                self.sleep(0.05 * (2 ** (attempt - 1)))
            except Exception:
                return err("database_error", "Backend operation failed")
        return err("service_unavailable", "Retry budget exhausted", True)

    def _validated_write(self, name, args, event):
        """Perform one approved write. Do not retry after an ambiguous outcome."""
        event["attempts"] = 1
        event["decision"] = "executed"
        try:
            if name == "create_reservation":
                result = self._create_reservation(args)
            elif name == "cancel_reservation":
                result = self._cancel_reservation(args)
            else:
                result = self._update_reservation(args)
            issue = next(Draft202012Validator(
                CONTRACTS[name]["output_schema"], format_checker=FormatChecker()
            ).iter_errors(result), None)
            return err("invalid_output", "Write result violates output contract") if issue else result
        except TransientBackendError:
            return err("write_outcome_unknown",
                       "Could not confirm write outcome. Check reservations before attempting again.")
        except Exception:
            return err("database_error",
                       "Write failed or outcome uncertain. Check reservations before attempting again.")

    def _find_rooms(self, args):
        day = args["date"]
        candidates = []
        for room in self.backend.list_rooms():
            if (room["Capacity"] < args["min_capacity"] or
                room["ComputerCount"] < args.get("min_computers", 0) or
                (args["require_projector"] and not room["HasProjector"])):
                continue
            free = windows(self.backend.busy_ranges(room["RoomID"],
                datetime.fromisoformat(day)), day)
            start, end = args.get("start_time"), args.get("end_time")
            if start is not None and not includes(free, start, end):
                continue
            item = dict(room)
            item["HasProjector"] = bool(item["HasProjector"])
            item["available_slots"] = free
            candidates.append(item)
        candidates.sort(key=lambda room: (
            room["Capacity"], room["ComputerCount"], room["RoomID"]
        ))
        return ok({"rooms": candidates[:5]})

    def _get_availability(self, args):
        room = self.backend.room_by_id(args["room_id"])
        if room is None:
            return err("room_not_found", "Room does not exist")
        return ok({"room_id": args["room_id"], "date": args["date"],
                   "free_windows": windows(self.backend.busy_ranges(
                       args["room_id"], datetime.fromisoformat(args["date"])), args["date"])})

    def _create_reservation(self, args):
        """Validate intent and room, then let the backend recheck atomically."""
        room = self.backend.room_by_id(args["room_id"])
        if room is None:
            return err("room_not_found", "Room does not exist")
        if not args["event_name"].strip():
            return err("invalid_input", "Event name cannot be blank")
        if args["student_count"] > room["Capacity"]:
            return err("capacity_exceeded", "Room capacity is too small")
        if room["ComputerCount"] < args.get("min_computers", 0):
            return err("equipment_unavailable", "Not enough computers")
        if args.get("require_projector", False) and not room["HasProjector"]:
            return err("equipment_unavailable", "Room has no projector")

        start = datetime.fromisoformat(f'{args["date"]}T{args["start_time"]}')
        end = datetime.fromisoformat(f'{args["date"]}T{args["end_time"]}')
        reservation_id = self.backend.create_reservation_atomic(
            room_id=args["room_id"], event_name=args["event_name"].strip(),
            event_type=args["event_type"], start=start, end=end,
            student_count=args["student_count"],
            min_computers=args.get("min_computers", 0),
            require_projector=args.get("require_projector", False),
        )
        if reservation_id is None:
            return err("room_unavailable", "Room became unavailable or no longer meets requirements")
        return ok({
            "reservation_id": reservation_id,
            "room_id": args["room_id"],
            "event_name": args["event_name"].strip(),
            "date": args["date"],
            "start_time": args["start_time"],
            "end_time": args["end_time"],
        })

    def _cancel_reservation(self, args):
        """Delete one approved booking by ID; the backend returns the deleted row."""
        deleted = self.backend.cancel_reservation_atomic(args["reservation_id"])
        if deleted is None:
            return err("reservation_not_found", "Reservation does not exist or was already cancelled")
        return ok({
            "reservation_id": int(deleted["ReservationID"]),
            "room_id": int(deleted["RoomID"]),
            "date": deleted["StartTime"].date().isoformat(),
            "start_time": deleted["StartTime"].strftime("%H:%M"),
            "end_time": deleted["EndTime"].strftime("%H:%M"),
        })

    def _update_reservation(self, args):
        """Partial booking edit; the backend atomically checks stale data and conflicts.

        No automatic write retries. The trusted app confirms exact proposed changes
        before invoking run(..., approved=True).
        """
        previous = self.backend.reservation_by_id(args["reservation_id"])
        if previous is None:
            return err("reservation_not_found", "Reservation does not exist")

        room_id = args.get("room_id", int(previous["RoomID"]))
        event_name = args.get("event_name", previous["EventName"]).strip()
        event_type = args.get("event_type", previous["EventType"])
        student_count = args.get("student_count", int(previous["StudentCount"]))
        day = args.get("date", previous["StartTime"].date().isoformat())
        start_time = args.get("start_time", previous["StartTime"].strftime("%H:%M"))
        end_time = args.get("end_time", previous["EndTime"].strftime("%H:%M"))
        if not event_name:
            return err("invalid_input", "Event name cannot be blank")
        if date.fromisoformat(day).weekday() not in WORKING_DAYS:
            return err("invalid_input", "College is closed on Friday and Saturday")
        if start_time < OPEN or end_time > CLOSE or start_time >= end_time:
            return err("invalid_input", "Time must be increasing and within 08:00–22:00")

        room = self.backend.room_by_id(room_id)
        if room is None:
            return err("room_not_found", "Target room does not exist")
        if student_count > room["Capacity"]:
            return err("capacity_exceeded", "Target room capacity is too small")
        if room["ComputerCount"] < args.get("min_computers", 0):
            return err("equipment_unavailable", "Not enough computers in target room")
        if args.get("require_projector", False) and not room["HasProjector"]:
            return err("equipment_unavailable", "Target room has no projector")

        start = datetime.fromisoformat(f"{day}T{start_time}")
        end = datetime.fromisoformat(f"{day}T{end_time}")
        updated = self.backend.update_reservation_atomic(
            reservation_id=args["reservation_id"], expected=previous,
            room_id=room_id, event_name=event_name, event_type=event_type,
            start=start, end=end, student_count=student_count,
            min_computers=args.get("min_computers", 0),
            require_projector=args.get("require_projector", False),
        )
        if updated is None:
            return err("reservation_unavailable",
                       "Booking changed or the target room is no longer suitable/free")
        return ok({
            "reservation_id": int(updated["ReservationID"]),
            "room_id": int(updated["RoomID"]),
            "event_name": updated["EventName"],
            "date": updated["StartTime"].date().isoformat(),
            "start_time": updated["StartTime"].strftime("%H:%M"),
            "end_time": updated["EndTime"].strftime("%H:%M"),
            "student_count": int(updated["StudentCount"]),
        })
