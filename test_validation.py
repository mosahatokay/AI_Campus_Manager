
import json
from jsonschema import validate, FormatChecker, ValidationError

with open("tool_contract.json", encoding="utf-8") as file:
    contract = json.load(file)

request = {
    "date": "2026-11-04",
    "min_capacity": 40,
    "min_computers": 20,
    "require_projector": True,
    "start_time": "10:00",
    "end_time": "12:00"
}


try:
    validate(
        instance=request,
        schema=contract["input_schema"],
        format_checker=FormatChecker()
    )
    print("Input is valid!")

except ValidationError as e:
    error = {
        "status": "error",
        "error": {
            "type": "invalid_input",
            "message": e.message,
            "retryable": False
        }
    }
    print(error)

