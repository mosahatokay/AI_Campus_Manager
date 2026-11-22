# AI Campus Manager — initial dual-backend foundation

**This is a first incremental draft, not a complete milestone-1 submission.**

- Original SQL Server implementation is preserved in `main.py`, with the original contract files unchanged.
- New read-only tools are available in `src/tools.py`, behind either `src/mock_backend.py` (Colab, entirely in memory) or `src/sql_backend.py` (optional, local SQL Server).
- The mock generates 120 rooms and 6 synthetic bookings. These are **not** exports of the user's database. No personal information or credentials are included.
- Friday/Saturday unavailable; time windows 08:00–22:00; find-rooms results sorted by closest sufficient capacity and then computer count.

## Run locally (or in Colab after copying/cloning project)

```bash
pip install -r requirements.txt
python -m pytest -q
python -m src.demo
```

To use the SQL backend with the new tool wrapper, install `pyodbc` **locally** and an ODBC Driver 17/18 for SQL Server, and set the server via environment variable `CAMPUS_SQL_SERVER`. Then in Python:

```python
from src.sql_backend import SQLServerBackend
from src.tools import CampusTools
backend = SQLServerBackend()  # Windows Authentication against local CampusAI
try:
    tools = CampusTools(backend)
    result = tools.run('get_availability', {'room_id': 4, 'date': '2026-12-02'})
    print(result)
finally:
    backend.close()
```

**Important:** SQL mode was not tested here against your local SQL Server. The original `main.py` remains unchanged. The Colab demo uses mock mode only.

## Google Colab

The included `CampusAI_demo.ipynb` runs the same mock demo. For submission, put all files into your own Git repository, replace `REPOSITORY_URL_HERE` in the notebook with the Git URL, and add its *Open in Colab* link to this README. The final notebook must clone the committed repo from scratch.

## Still missing for milestone 1

The approved tool list must be verified against the actual proposal. This iteration implements only two read tools, **not** create/cancel/update. A full agent loop with model decision, state and separated conversations, history comparison, a full trace per run, docs, AI-usage appendix, and Colab from Git are not yet included.
