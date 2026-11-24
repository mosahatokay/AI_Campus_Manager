"""Opt-in SQL Server backend. Uses the existing CampusAI tables; never connects on import.

SQL backend is for local machines with SQL Server + ODBC, not for standalone Colab.
No credentials are stored in source code.
"""
from __future__ import annotations
import os
from .mock_backend import TransientBackendError


class SQLServerBackend:
    def __init__(self, server=None):
        try:
            import pyodbc
        except ImportError as exc:
            raise RuntimeError("Install pyodbc locally to use SQL Server mode") from exc
        drivers = pyodbc.drivers()
        driver = next((name for name in (
            "ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server"
        ) if name in drivers), None)
        if driver is None:
            raise RuntimeError("No SQL Server ODBC driver installed")
        server = server or os.getenv("CAMPUS_SQL_SERVER")
        if not server:
            raise RuntimeError("Set CAMPUS_SQL_SERVER to your SQL Server instance")
        self.pyodbc = pyodbc
        self.connection = pyodbc.connect(
            f"DRIVER={{{driver}}};SERVER={server};DATABASE=CampusAI;"
            "Trusted_Connection=yes;TrustServerCertificate=yes;", timeout=5
        )

    def query(self, statement, *params):
        try:
            cur = self.connection.cursor()
            cur.execute(statement, *params)
            return cur
        except self.pyodbc.Error as exc:
            code = str(exc.args[0]) if exc.args else ""
            if code in {"08S01", "HYT00", "HYT01", "40001"}:
                raise TransientBackendError("SQL Server temporarily unavailable") from exc
            raise

    def list_rooms(self):
        cur = self.query("""SELECT RoomID, BuildingID, FloorNumber, RoomNumber,
            Capacity, ComputerCount, HasProjector FROM dbo.Rooms""")
        columns = [column[0] for column in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]

    def room_by_id(self, room_id):
        cur = self.query("""SELECT RoomID, BuildingID, FloorNumber, RoomNumber,
            Capacity, ComputerCount, HasProjector FROM dbo.Rooms WHERE RoomID = ?""", room_id)
        row = cur.fetchone()
        return dict(zip((column[0] for column in cur.description), row)) if row else None

    def busy_ranges(self, room_id, day):
        from datetime import timedelta
        cur = self.query("""SELECT StartTime, EndTime FROM dbo.Reservations
            WHERE RoomID = ? AND StartTime < ? AND EndTime > ?
            ORDER BY StartTime""", room_id, day + timedelta(days=1), day)
        return [(r[0], r[1]) for r in cur.fetchall()]

    def list_exams(self, *, day, building_id=None, room_id=None, start=None, end=None):
        """Read only scheduled exams; optional filters are SQL parameters, never concatenated."""
        from datetime import timedelta
        statement = """SELECT res.ReservationID, res.RoomID, room.BuildingID,
                room.FloorNumber, room.RoomNumber, res.EventName,
                res.StartTime, res.EndTime, res.StudentCount
            FROM dbo.Reservations AS res
            JOIN dbo.Rooms AS room ON room.RoomID = res.RoomID
            WHERE res.EventType = 'Exam'
              AND res.StartTime < ? AND res.EndTime > ?"""
        params = [day + timedelta(days=1), day]
        if building_id is not None:
            statement += " AND room.BuildingID = ?"
            params.append(building_id)
        if room_id is not None:
            statement += " AND res.RoomID = ?"
            params.append(room_id)
        if start is not None:
            statement += " AND res.StartTime < ? AND res.EndTime > ?"
            params.extend([end, start])
        statement += " ORDER BY res.StartTime, res.RoomID, res.ReservationID"
        cur = self.query(statement, *params)
        columns = [column[0] for column in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]

    def create_reservation_atomic(self, *, room_id, event_name, event_type, start, end,
                                  student_count, min_computers=0, require_projector=False):
        """Insert only if still valid/free; row/range locks protect concurrent writes.

        No automatic retries: the caller must not repeat an uncertain write.
        The existing database schema is dbo.Rooms / dbo.Reservations.
        """
        # pyodbc defaults to autocommit=False. The context commits on normal
        # exit and rolls back if any exception occurs.
        with self.connection:
            cur = self.connection.cursor()
            cur.execute("""
                INSERT INTO dbo.Reservations
                    (RoomID, EventName, EventType, StartTime, EndTime, StudentCount)
                OUTPUT INSERTED.ReservationID
                SELECT r.RoomID, ?, ?, ?, ?, ?
                FROM dbo.Rooms AS r WITH (UPDLOCK, HOLDLOCK)
                WHERE r.RoomID = ?
                  AND r.Capacity >= ?
                  AND r.ComputerCount >= ?
                  AND (? = 0 OR r.HasProjector = 1)
                  AND NOT EXISTS (
                      SELECT 1 FROM dbo.Reservations AS x WITH (UPDLOCK, HOLDLOCK)
                      WHERE x.RoomID = r.RoomID
                        AND x.StartTime < ? AND x.EndTime > ?
                  )
            """, event_name, event_type, start, end, student_count,
                 room_id, student_count, min_computers, int(require_projector),
                 end, start)
            row = cur.fetchone()
            return int(row[0]) if row else None

    def cancel_reservation_atomic(self, reservation_id):
        """Delete one reservation using a single atomic statement and return its details.

        Transaction commits on success and rolls back on exception.
        The caller must not blindly retry when the outcome is uncertain.
        """
        with self.connection:
            cur = self.connection.cursor()
            cur.execute("""
                DELETE FROM dbo.Reservations
                OUTPUT DELETED.ReservationID, DELETED.RoomID,
                       DELETED.StartTime, DELETED.EndTime
                WHERE ReservationID = ?
            """, reservation_id)
            row = cur.fetchone()
            if row is None:
                return None
            return {
                "ReservationID": int(row[0]), "RoomID": int(row[1]),
                "StartTime": row[2], "EndTime": row[3],
            }

    def reservation_by_id(self, reservation_id):
        """Read the current full booking; caller never updates without confirmation."""
        cur = self.query("""SELECT ReservationID, RoomID, EventName, EventType,
                                 StartTime, EndTime, StudentCount
                          FROM dbo.Reservations WHERE ReservationID = ?""", reservation_id)
        row = cur.fetchone()
        return dict(zip((column[0] for column in cur.description), row)) if row else None

    def update_reservation_atomic(self, *, reservation_id, expected, room_id,
                                  event_name, event_type, start, end, student_count,
                                  min_computers=0, require_projector=False):
        """Compare-and-update in one transaction, without retrying uncertain writes.

        Locks the booking/target room and checks time overlaps excluding the
        reservation itself. Matches original values to reject stale updates.
        """
        with self.connection:
            cur = self.connection.cursor()
            cur.execute("""
                UPDATE booking
                SET RoomID = ?, EventName = ?, EventType = ?,
                    StartTime = ?, EndTime = ?, StudentCount = ?
                OUTPUT INSERTED.ReservationID, INSERTED.RoomID,
                       INSERTED.EventName, INSERTED.StartTime,
                       INSERTED.EndTime, INSERTED.StudentCount
                FROM dbo.Reservations AS booking WITH (UPDLOCK, HOLDLOCK)
                INNER JOIN dbo.Rooms AS room WITH (UPDLOCK, HOLDLOCK)
                    ON room.RoomID = ?
                WHERE booking.ReservationID = ?
                  AND booking.RoomID = ?
                  AND booking.EventName = ?
                  AND booking.EventType = ?
                  AND booking.StartTime = ?
                  AND booking.EndTime = ?
                  AND booking.StudentCount = ?
                  AND room.Capacity >= ?
                  AND room.ComputerCount >= ?
                  AND (? = 0 OR room.HasProjector = 1)
                  AND NOT EXISTS (
                      SELECT 1 FROM dbo.Reservations AS conflict WITH (UPDLOCK, HOLDLOCK)
                      WHERE conflict.RoomID = room.RoomID
                        AND conflict.ReservationID <> booking.ReservationID
                        AND conflict.StartTime < ? AND conflict.EndTime > ?
                  )
            """, room_id, event_name, event_type, start, end, student_count,
                 room_id, reservation_id,
                 expected["RoomID"], expected["EventName"], expected["EventType"],
                 expected["StartTime"], expected["EndTime"], expected["StudentCount"],
                 student_count, min_computers, int(require_projector), end, start)
            row = cur.fetchone()
            if row is None:
                return None
            return {
                "ReservationID": int(row[0]), "RoomID": int(row[1]),
                "EventName": row[2], "StartTime": row[3],
                "EndTime": row[4], "StudentCount": int(row[5]),
            }

    def close(self):
        self.connection.close()
