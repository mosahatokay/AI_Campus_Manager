"""Validated read-only tools, with interchangeable SQL Server / synthetic mock backends."""
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

    def run(self, name, args):
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
            else:
                result = self._validated_run(name, args, event)
        event["status"] = result["status"]
        if result["status"] == "error":
            event["reason"] = result["error"]["type"]
        event["latency_ms"] = round((time.perf_counter() - began) * 1000, 2)
        self.trace.append(event)
        return result

    def _validated_run(self, name, args, event):
        day = date.fromisoformat(args["date"])
        if day.weekday() not in WORKING_DAYS:
            return err("invalid_input", "College is closed on Friday and Saturday")
        if name == "find_rooms":
            start, end = args.get("start_time"), args.get("end_time")
            if start is not None and (start < OPEN or end > CLOSE or start >= end):
                return err("invalid_input", "Time must be increasing and within 08:00–22:00")
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
