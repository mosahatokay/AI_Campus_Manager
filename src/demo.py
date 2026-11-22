"""Repeatable mock demonstration: no SQL Server and no API key needed."""
import json
from pathlib import Path
from .mock_backend import MockBackend
from .tools import CampusTools


def run_demo(save_traces=False):
    tools = CampusTools(MockBackend())
    request = {"date": "2026-12-02", "min_capacity": 40, "min_computers": 20,
               "require_projector": True, "start_time": "10:00", "end_time": "12:00"}
    found = tools.run("find_rooms", request)
    print("Room search:", json.dumps(found, ensure_ascii=False, indent=2))
    availability = tools.run("get_availability", {"room_id": 4, "date": "2026-12-02"})
    print("Availability:", json.dumps(availability, ensure_ascii=False, indent=2))
    if save_traces:
        folder = Path("docs/traces")
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "mock_read_tools.json").write_text(
            json.dumps(tools.trace, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    run_demo(save_traces=True)
