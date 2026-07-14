import datetime
import sqlite3
from registry import tool
from routines import calculate_next_run, get_db_connection, init_db

@tool
def create_routine(name: str, schedule: str, type: str, action: str, timeout: int = 300):
    """Creates a new routine (scheduled task).
    name: Unique name for the routine.
    schedule: Cron expression (e.g. '*/5 * * * *') or interval (e.g. '10s', '5m', '1h').
    type: Type of action, either 'shell' (to run a terminal command) or 'prompt' (to run an agent prompt).
    action: The CLI command or the agent prompt to run.
    timeout: Maximum execution timeout in seconds.
    """
    init_db()
    if type not in ("shell", "prompt"):
        return "Error: type must be either 'shell' or 'prompt'."
    
    now = datetime.datetime.now()
    try:
        next_run = calculate_next_run(schedule, now)
    except Exception as e:
        return f"Error parsing schedule '{schedule}': {e}"

    try:
        with get_db_connection() as conn:
            conn.execute(
                "INSERT INTO routines (name, schedule, type, action, status, timeout, created_at, next_run) VALUES (?, ?, ?, ?, 'active', ?, ?, ?)",
                (name, schedule, type, action, timeout, now.isoformat(), next_run.isoformat())
            )
            conn.commit()
        return f"Successfully created routine '{name}'. First scheduled run: {next_run.strftime('%Y-%m-%d %H:%M:%S')}."
    except sqlite3.IntegrityError:
        return f"Error: Routine with name '{name}' already exists."
    except Exception as e:
        return f"Error: {e}"

@tool
def list_routines():
    """Lists all configured routines, their schedules, types, statuses, and next run times."""
    init_db()
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM routines ORDER BY name ASC")
            rows = cursor.fetchall()
            if not rows:
                return "No routines configured."
            
            output = ["Configured Routines:"]
            for r in rows:
                last_run = r["last_run"] or "Never"
                next_run = r["next_run"]
                if last_run != "Never":
                    last_run = last_run[:19].replace("T", " ")
                next_run = next_run[:19].replace("T", " ")
                output.append(
                    f"- {r['name']} | Schedule: {r['schedule']} | Type: {r['type']} | Status: {r['status']} | Last Run: {last_run} | Next Run: {next_run}"
                )
            return "\n".join(output)
    except Exception as e:
        return f"Error: {e}"

@tool
def pause_routine(name: str):
    """Pauses an active routine so it will not be executed by the scheduler."""
    init_db()
    try:
        with get_db_connection() as conn:
            cursor = conn.execute("UPDATE routines SET status = 'paused' WHERE name = ?", (name,))
            conn.commit()
            if cursor.rowcount > 0:
                return f"Successfully paused routine '{name}'."
            else:
                return f"Routine '{name}' not found."
    except Exception as e:
        return f"Error: {e}"

@tool
def resume_routine(name: str):
    """Resumes a paused routine, recalculating its next run time."""
    init_db()
    now = datetime.datetime.now()
    try:
        with get_db_connection() as conn:
            cursor = conn.execute("SELECT schedule FROM routines WHERE name = ?", (name,))
            row = cursor.fetchone()
            if not row:
                return f"Routine '{name}' not found."
            
            try:
                next_run = calculate_next_run(row["schedule"], now)
            except Exception:
                next_run = now

            conn.execute("UPDATE routines SET status = 'active', next_run = ? WHERE name = ?", (next_run.isoformat(), name))
            conn.commit()
        return f"Successfully resumed routine '{name}'. Next run: {next_run.strftime('%Y-%m-%d %H:%M:%S')}."
    except Exception as e:
        return f"Error: {e}"

@tool
def delete_routine(name: str):
    """Deletes a routine and its execution history logs."""
    init_db()
    try:
        with get_db_connection() as conn:
            cursor = conn.execute("DELETE FROM routines WHERE name = ?", (name,))
            conn.commit()
            if cursor.rowcount > 0:
                return f"Successfully deleted routine '{name}'."
            else:
                return f"Routine '{name}' not found."
    except Exception as e:
        return f"Error: {e}"

@tool
def view_routine_logs(name: str, limit: int = 10):
    """Retrieves the recent execution logs for a specific routine."""
    init_db()
    try:
        with get_db_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM routine_logs WHERE routine_name = ? ORDER BY triggered_at DESC LIMIT ?",
                (name, limit)
            )
            rows = cursor.fetchall()
            if not rows:
                return f"No logs found for routine '{name}'."
            
            output = [f"Logs for routine '{name}' (showing last {limit}):"]
            for r in rows:
                trig = r["triggered_at"][:19].replace("T", " ")
                fin = r["finished_at"][:19].replace("T", " ") if r["finished_at"] else "N/A"
                log_str = f"Log ID: {r['id']} | Triggered: {trig} | Finished: {fin} | Status: {r['status']}"
                if r["output"]:
                    log_str += f"\n  Output: {r['output'].strip()}"
                if r["error"]:
                    log_str += f"\n  Error: {r['error'].strip()}"
                output.append(log_str)
            return "\n".join(output)
    except Exception as e:
        return f"Error: {e}"
