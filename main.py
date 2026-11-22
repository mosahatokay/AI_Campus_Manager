
import pyodbc

import json
from jsonschema import validate, FormatChecker, ValidationError

from datetime import date , datetime 
import time

from pathlib import Path

def save_log(entry):
    log_file = Path(__file__).parent / "execution_log.jsonl"

    with open(log_file, "a", encoding="utf-8") as file:
        file.write(json.dumps(entry, ensure_ascii=False) + "\n")


drivers = pyodbc.drivers()
print("Available drivers:", drivers)

driver = next(
    (d for d in ["ODBC Driver 18 for SQL Server",
                 "ODBC Driver 17 for SQL Server"]
     if d in drivers),
    None
)

if driver is None:
    print("SQL Server ODBC driver not found.")
else:
    server = r"LAPTOP-GQHR6ETG\SQLSERVER"

    connection = pyodbc.connect(
        f"DRIVER={{{driver}}};"
        f"SERVER={server};"
        "DATABASE=CampusAI;"
        "Trusted_Connection=yes;"
        "TrustServerCertificate=yes;",
        timeout=5
    )     
    cursor = connection.cursor()
    
    with open("tool_contract.json", encoding="utf-8") as file:
        contract = json.load(file)


   
    
    
    
    
   
    def find_rooms(min_capacity, min_computers, require_projector, start_time, end_time):
        cursor.execute("""
            SELECT TOP (5) r.*
            FROM dbo.Rooms AS r
            WHERE r.Capacity >= ?
              AND r.ComputerCount >= ?
              AND r.HasProjector >= ?
              AND NOT EXISTS (
                  SELECT 1
                  FROM dbo.Reservations AS res
                  WHERE res.RoomID = r.RoomID
                    AND res.StartTime < ?
                    AND res.EndTime > ?
              )
            ORDER BY r.RoomID
        """, min_capacity, min_computers, int(require_projector),
             end_time, start_time)

        
        columns = [column[0] for column in cursor.description]

        rooms = [
            dict(zip(columns, row))
            for row in cursor.fetchall()
        ]

        return {
            "status": "ok",
            "data": {
                "rooms": rooms
            }
        }

        
    def get_availability(room_id, requested_date):
        # Validate input
        input_schema = {
            "type": "object",
            "properties": {
                "room_id": {"type": "integer", "minimum": 1},
                "date": {"type": "string", "format": "date"}
            },
            "required": ["room_id", "date"],
            "additionalProperties": False
        }

        try:
            validate(
                {"room_id": room_id, "date": requested_date},
                input_schema,
                format_checker=FormatChecker()
            )
        except ValidationError as e:
            return {
                "status": "error",
                "error": {
                    "type": "invalid_input",
                    "message": e.message,
                    "retryable": False
                }
            }

        requested_day = date.fromisoformat(requested_date)
        day_name = requested_day.strftime("%A")

        if day_name not in contract["business_rules"]["working_days"]:
            return {
                "status": "error",
                "error": {
                    "type": "invalid_input",
                    "message": "College is closed on this day",
                    "retryable": False
                }
            }

        opening = contract["business_rules"]["opening_time"]
        closing = contract["business_rules"]["closing_time"]

        day_start = datetime.fromisoformat(
            f"{requested_date}T{opening}"
        )
        day_end = datetime.fromisoformat(
            f"{requested_date}T{closing}"
        )

        # Check room exists
        cursor.execute(
            "SELECT 1 FROM dbo.Rooms WHERE RoomID = ?",
            room_id
        )

        if cursor.fetchone() is None:
            return {
                "status": "error",
                "error": {
                    "type": "room_not_found",
                    "message": "Room does not exist",
                    "retryable": False
                }
            }

        # Get existing reservations
        cursor.execute("""
            SELECT StartTime, EndTime
            FROM dbo.Reservations
            WHERE RoomID = ?
              AND StartTime < ?
              AND EndTime > ?
            ORDER BY StartTime
        """, room_id, day_end, day_start)

        reservations = cursor.fetchall()
        free_windows = []
        current = day_start

        for busy_start, busy_end in reservations:
            busy_start = max(busy_start, day_start)
            busy_end = min(busy_end, day_end)

            if busy_start > current:
                free_windows.append({
                    "start": current.strftime("%H:%M"),
                    "end": busy_start.strftime("%H:%M")
                })

            current = max(current, busy_end)

        if current < day_end:
            free_windows.append({
                "start": current.strftime("%H:%M"),
                "end": day_end.strftime("%H:%M")
            })

        return {
            "status": "ok",
            "data": {
                "room_id": room_id,
                "date": requested_date,
                "free_windows": free_windows
            }
        }

    def run_search_with_retry(*args):
        transient_errors = {"08S01", "HYT00", "HYT01", "40001"}

        for attempt in range(1, 4):
            try:
                
               

                return find_rooms(*args), attempt

            except pyodbc.Error as e:
                error_code = str(e.args[0]) if e.args else ""

                if error_code not in transient_errors:
                    raise

                
                if attempt == 3:
                    return {
                        "status": "error",
                        "error": {
                            "type": "service_unavailable",
                            "message": "SQL search failed after 3 attempts",
                            "retryable": True
                        }
                    }, attempt

                time.sleep(0.5 * (2 ** (attempt - 1)))

    print("Testing get_availability:")

    availability_result = get_availability(
        1,
        "2026-11-02"
    )

    print(json.dumps(
        availability_result,
        indent=2,
        ensure_ascii=False
    ))

    request = {
        "date": "2026-11-04",
        "min_capacity": 40,
        "min_computers": 0,
        "require_projector": False,
        "start_time": "08:00",
        "end_time": "20:00"
        
    }

    try:
        validate(
            instance=request,
            schema=contract["input_schema"],
            format_checker=FormatChecker()
            
        )

        if request["start_time"] >= request["end_time"]:
            raise ValidationError(
                "End time must be later than start time"
            )
        
        weekday_names = [
            "Monday", "Tuesday", "Wednesday",
            "Thursday", "Friday", "Saturday", "Sunday"
        ]

        requested_day = date.fromisoformat(request["date"])
        day_name = weekday_names[requested_day.weekday()]

        if day_name not in contract["business_rules"]["working_days"]:
            raise ValidationError(
                "College is closed on this day"
            )
        
        opening_time = contract["business_rules"]["opening_time"]
        closing_time = contract["business_rules"]["closing_time"]

        if (request["start_time"] < opening_time or
                request["end_time"] > closing_time):
            raise ValidationError(
                "Requested time is outside college working hours"
            )



        start_time = request["date"] + "T" + request["start_time"] + ":00"
        end_time = request["date"] + "T" + request["end_time"] + ":00"

        
        start_measure = time.perf_counter()
        result  , attempts = run_search_with_retry(
            request["min_capacity"],
            request["min_computers"],
            request["require_projector"],
            start_time,
            end_time
        )

        elapsed_ms = round(
            (time.perf_counter() - start_measure) * 1000
        )

        print("Execution time:", elapsed_ms, "ms")
        
        
        log_entry = {
            "tool": "find_rooms",
            "decision": "executed",
            "status": result["status"],
            "attempts": attempts,
            "latency_ms": elapsed_ms
        }


        print("Execution log:", log_entry)

        save_log(log_entry)


        validate(
            instance=result,
            schema=contract["output_schema"],
            format_checker=FormatChecker()
        )

        print("Output is valid!")

        print(json.dumps(result, indent=2, ensure_ascii=False))


    except ValidationError as e:
        
        rejected_log = {
            "tool": "find_rooms",
            "decision": "rejected",
            "status": "error",
            "attempts": 0,
            "reason": e.message
        }

        print("Execution log:", rejected_log)

        save_log(rejected_log)

        print({
            "status": "error",
            "error": {
                "type": "invalid_input",
                "message": e.message,
                "retryable": False
            }
        })




    

    connection.close()
