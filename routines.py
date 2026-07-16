import os
import sys
import sqlite3
import datetime
import time
import subprocess
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from concurrency import global_executor

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "routines.db")

def get_db_connection():
    """Returns a sqlite3 connection in WAL mode with a busy timeout."""
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn

def init_db():
    """Initializes tables and indexes."""
    with get_db_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS routines (
                name TEXT PRIMARY KEY,
                schedule TEXT NOT NULL,
                type TEXT NOT NULL,
                action TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                timeout INTEGER NOT NULL DEFAULT 300,
                created_at TIMESTAMP NOT NULL,
                last_run TIMESTAMP,
                next_run TIMESTAMP NOT NULL
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS routine_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                routine_name TEXT NOT NULL,
                status TEXT NOT NULL,
                triggered_at TIMESTAMP NOT NULL,
                finished_at TIMESTAMP,
                output TEXT,
                error TEXT,
                FOREIGN KEY (routine_name) REFERENCES routines(name) ON DELETE CASCADE
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pipelines (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                definition TEXT NOT NULL, -- JSON definition of variables and steps
                created_at TIMESTAMP NOT NULL
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pipeline_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pipeline_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                inputs TEXT NOT NULL, -- JSON input variables
                outputs TEXT, -- JSON variables/step outputs after execution
                triggered_at TIMESTAMP NOT NULL,
                finished_at TIMESTAMP,
                error TEXT,
                FOREIGN KEY (pipeline_id) REFERENCES pipelines(id) ON DELETE CASCADE
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pipeline_run_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                step_id TEXT NOT NULL,
                step_name TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TIMESTAMP NOT NULL,
                finished_at TIMESTAMP,
                output TEXT,
                error TEXT,
                FOREIGN KEY (run_id) REFERENCES pipeline_runs(id) ON DELETE CASCADE
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memory_nodes (
                id TEXT PRIMARY KEY,
                topic TEXT NOT NULL,
                keywords TEXT NOT NULL,
                summary TEXT NOT NULL,
                parent_id TEXT,
                last_updated TIMESTAMP NOT NULL
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_routines_status_next_run ON routines(status, next_run);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_routine_logs_name_triggered ON routine_logs(routine_name, triggered_at);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pipeline_runs_pid_status ON pipeline_runs(pipeline_id, status);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pipeline_run_logs_run_id ON pipeline_run_logs(run_id);")
        conn.commit()

# --- Lightweight Cron & Interval Parser ---

def parse_cron_field(field, min_val, max_val):
    """Parses a single cron field and returns a set of valid values."""
    values = set()
    for part in field.split(","):
        if "/" in part:
            val_range, step = part.split("/")
            step = int(step)
            if val_range == "*":
                r_start, r_end = min_val, max_val
            elif "-" in val_range:
                r_start, r_end = map(int, val_range.split("-"))
            else:
                r_start = int(val_range)
                r_end = max_val
            for v in range(r_start, r_end + 1, step):
                if min_val <= v <= max_val:
                    values.add(v)
        elif "-" in part:
            start, end = map(int, part.split("-"))
            for v in range(start, end + 1):
                if min_val <= v <= max_val:
                    values.add(v)
        elif part == "*":
            return set(range(min_val, max_val + 1))
        else:
            v = int(part)
            if min_val <= v <= max_val:
                values.add(v)
    return values

def get_next_cron_run(cron_expr, start_time):
    """Calculates the next datetime matching a 5-field cron expression."""
    fields = cron_expr.strip().split()
    if len(fields) != 5:
        raise ValueError("Cron expression must have exactly 5 fields.")

    min_set = parse_cron_field(fields[0], 0, 59)
    hour_set = parse_cron_field(fields[1], 0, 23)
    dom_set = parse_cron_field(fields[2], 1, 31)
    month_set = parse_cron_field(fields[3], 1, 12)
    # Day of week: standard is 0-6 (Sunday=0), sometimes 7 is Sunday. Map 7 to 0.
    dow_raw = parse_cron_field(fields[4], 0, 7)
    dow_set = {0 if d == 7 else d for d in dow_raw}

    # Truncate start_time to minute, and increment by 1 minute to find the next run
    current = start_time.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)
    
    # Bound search to 1 year to prevent infinite loops
    limit = current + datetime.timedelta(days=366)
    while current < limit:
        if current.month in month_set:
            if current.day in dom_set:
                py_dow = current.weekday()
                cron_dow = (py_dow + 1) % 7
                if cron_dow in dow_set:
                    if current.hour in hour_set:
                        if current.minute in min_set:
                            return current
        current += datetime.timedelta(minutes=1)
    raise ValueError("No matching execution time found within 1 year.")

def parse_interval(interval_str):
    """Parses interval like 10s, 5m, 2h, 1d and returns seconds."""
    unit = interval_str[-1].lower()
    value = int(interval_str[:-1])
    if unit == "s":
        return value
    elif unit == "m":
        return value * 60
    elif unit == "h":
        return value * 3600
    elif unit == "d":
        return value * 86400
    else:
        raise ValueError(f"Unknown interval unit in '{interval_str}'")

def calculate_next_run(schedule_str, last_run_or_now):
    """Calculates next run datetime based on cron expression or interval string."""
    schedule_str = schedule_str.strip()
    if len(schedule_str.split()) == 5:
        return get_next_cron_run(schedule_str, last_run_or_now)
    else:
        seconds = parse_interval(schedule_str)
        return last_run_or_now + datetime.timedelta(seconds=seconds)

# --- Scheduler Implementation ---

class RoutinesScheduler:
    def __init__(self, max_workers=4, notification_callback=None):
        self.stop_event = threading.Event()
        self.executor = global_executor
        self.running_tasks = {} # routine_name -> future
        # Optional callback: fn(title, message, level) — injected by app.py to emit SocketIO notifications
        self.notification_callback = notification_callback

    def start(self):
        self.thread = threading.Thread(target=self._loop, name="RoutinesSchedulerLoop", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if hasattr(self, "thread"):
            self.thread.join()

    def _loop(self):
        init_db()
        while not self.stop_event.is_set():
            try:
                now = datetime.datetime.now()
                with get_db_connection() as conn:
                    # Select active routines that are due to run
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT * FROM routines WHERE status = 'active' AND next_run <= ?",
                        (now.isoformat(),)
                    )
                    due_routines = cursor.fetchall()
                    
                    for r in due_routines:
                        name = r["name"]
                        # Skip if it is already running
                        if name in self.running_tasks and not self.running_tasks[name].done():
                            continue
                        
                        # Calculate next run time
                        try:
                            next_run = calculate_next_run(r["schedule"], now)
                        except Exception as ex:
                            # If schedule calculation fails, log it and set to a default fallback of 5 minutes later
                            next_run = now + datetime.timedelta(minutes=5)
                            print(f"[Routines Scheduler] Error calculating schedule for '{name}': {ex}", file=sys.stderr)

                        # Update next_run and last_run immediately to avoid double execution on next check
                        conn.execute(
                            "UPDATE routines SET last_run = ?, next_run = ? WHERE name = ?",
                            (now.isoformat(), next_run.isoformat(), name)
                        )
                        conn.commit()

                        # Dispatch the job to the ThreadPoolExecutor
                        future = self.executor.submit(self._run_job_wrapper, dict(r), now)
                        self.running_tasks[name] = future

                # Prune finished tasks from running_tasks dict
                self.running_tasks = {k: v for k, v in self.running_tasks.items() if not v.done()}

            except Exception as e:
                print(f"[Routines Scheduler Error] Exception in loop: {traceback.format_exc()}", file=sys.stderr)
            
            # Sleep using event to allow instant interruption
            self.stop_event.wait(timeout=5.0)

    def _run_job_wrapper(self, routine, triggered_at):
        name = routine["name"]
        timeout = routine["timeout"]
        
        # Insert log entry as running
        log_id = None
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO routine_logs (routine_name, status, triggered_at) VALUES (?, 'running', ?)",
                    (name, triggered_at.isoformat())
                )
                conn.commit()
                log_id = cursor.lastrowid
        except Exception as e:
            print(f"[Routines Logger Error] Could not write initial log for '{name}': {e}", file=sys.stderr)

        # Execute routine action with timeout
        status = "success"
        output = ""
        error = ""
        
        try:
            if routine["type"] == "shell":
                # Execute shell action using a subprocess with timeout
                proc = subprocess.run(
                    routine["action"],
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=timeout
                )
                output = proc.stdout
                error = proc.stderr
                if proc.returncode != 0:
                    status = "failure"
                    if not error:
                        error = f"Process exited with non-zero code {proc.returncode}"
            elif routine["type"] == "prompt":
                # Dynamically load Agent & run the prompt
                from agent import Agent
                from config import SYSTEM_PROMPT
                agent = Agent(SYSTEM_PROMPT)
                
                # We consume the generator from agent.stream to execute it
                # and concatenate chunks into output
                chunks = []
                for chunk in agent.stream(routine["action"]):
                    chunks.append(chunk)
                output = "".join(chunks)
            else:
                raise ValueError(f"Unknown routine type: {routine['type']}")

        except subprocess.TimeoutExpired:
            status = "timeout"
            error = f"Execution exceeded timeout limit of {timeout} seconds."
        except Exception as e:
            status = "failure"
            error = f"Exception during execution:\n{traceback.format_exc()}"

        # Truncate logs output to max 50KB to preserve resource limits
        MAX_LOG_SIZE = 50 * 1024
        if len(output) > MAX_LOG_SIZE:
            output = output[-MAX_LOG_SIZE:] + "\n[Output truncated due to size limit]"
        if len(error) > MAX_LOG_SIZE:
            error = error[-MAX_LOG_SIZE:] + "\n[Error truncated due to size limit]"

        finished_at = datetime.datetime.now()

        # Update log status and rotate old logs to keep only last 100 entries per routine
        try:
            with get_db_connection() as conn:
                if log_id:
                    conn.execute(
                        "UPDATE routine_logs SET status = ?, finished_at = ?, output = ?, error = ? WHERE id = ?",
                        (status, finished_at.isoformat(), output, error, log_id)
                    )
                # Keep only last 100 logs for this routine
                conn.execute("""
                    DELETE FROM routine_logs WHERE id NOT IN (
                        SELECT id FROM routine_logs 
                        WHERE routine_name = ? 
                        ORDER BY triggered_at DESC 
                        LIMIT 100
                    ) AND routine_name = ?
                """, (name, name))
                conn.commit()
        except Exception as e:
            print(f"[Routines Logger Error] Could not finalize log for '{name}': {e}", file=sys.stderr)

        # Emit notification via injected callback (app.py wires this up)
        if self.notification_callback:
            try:
                if status == "success":
                    notif_title   = f"Routine '{name}' completed"
                    notif_message = (output.strip()[:120] + "...") if len(output.strip()) > 120 else (output.strip() or "Execution finished successfully.")
                    notif_level   = "success"
                elif status == "timeout":
                    notif_title   = f"Routine '{name}' timed out"
                    notif_message = error.strip()[:120] if error else f"Exceeded timeout of {timeout}s."
                    notif_level   = "warning"
                else:  # failure
                    notif_title   = f"Routine '{name}' failed"
                    notif_message = (error.strip()[:120] + "...") if len(error.strip()) > 120 else (error.strip() or "An unknown error occurred.")
                    notif_level   = "error"
                self.notification_callback(notif_title, notif_message, notif_level)
            except Exception as cb_err:
                print(f"[Routines Notifier] Could not emit notification for '{name}': {cb_err}", file=sys.stderr)

# --- CLI Implementation ---

def list_routines():
    init_db()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM routines ORDER BY name ASC")
        rows = cursor.fetchall()
        
        if not rows:
            print("No routines configured.")
            return

        header = f"{'Name':<15} | {'Schedule':<12} | {'Type':<6} | {'Status':<8} | {'Last Run':<20} | {'Next Run':<20}"
        print(header)
        print("-" * len(header))
        for r in rows:
            last_run = r["last_run"] or "Never"
            next_run = r["next_run"]
            if last_run != "Never":
                last_run = last_run[:19].replace("T", " ")
            next_run = next_run[:19].replace("T", " ")
            print(f"{r['name']:<15} | {r['schedule']:<12} | {r['type']:<6} | {r['status']:<8} | {last_run:<20} | {next_run:<20}")

def add_routine(name, schedule, type_name, action, timeout=300):
    init_db()
    now = datetime.datetime.now()
    try:
        next_run = calculate_next_run(schedule, now)
    except Exception as e:
        print(f"Error parsing schedule '{schedule}': {e}")
        sys.exit(1)

    with get_db_connection() as conn:
        try:
            conn.execute(
                "INSERT INTO routines (name, schedule, type, action, status, timeout, created_at, next_run) VALUES (?, ?, ?, ?, 'active', ?, ?, ?)",
                (name, schedule, type_name, action, timeout, now.isoformat(), next_run.isoformat())
            )
            conn.commit()
            print(f"Successfully added routine '{name}'. Next run: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
        except sqlite3.IntegrityError:
            print(f"Error: Routine with name '{name}' already exists.")
            sys.exit(1)

def delete_routine(name):
    init_db()
    with get_db_connection() as conn:
        cursor = conn.execute("DELETE FROM routines WHERE name = ?", (name,))
        conn.commit()
        if cursor.rowcount > 0:
            print(f"Deleted routine '{name}'.")
        else:
            print(f"Routine '{name}' not found.")

def pause_routine(name):
    init_db()
    with get_db_connection() as conn:
        cursor = conn.execute("UPDATE routines SET status = 'paused' WHERE name = ?", (name,))
        conn.commit()
        if cursor.rowcount > 0:
            print(f"Paused routine '{name}'.")
        else:
            print(f"Routine '{name}' not found.")

def resume_routine(name):
    init_db()
    now = datetime.datetime.now()
    with get_db_connection() as conn:
        cursor = conn.execute("SELECT schedule FROM routines WHERE name = ?", (name,))
        row = cursor.fetchone()
        if not row:
            print(f"Routine '{name}' not found.")
            return
        
        try:
            next_run = calculate_next_run(row["schedule"], now)
        except Exception as e:
            next_run = now

        conn.execute("UPDATE routines SET status = 'active', next_run = ? WHERE name = ?", (next_run.isoformat(), name))
        conn.commit()
        print(f"Resumed routine '{name}'. Next run: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")

def trigger_routine(name):
    init_db()
    with get_db_connection() as conn:
        cursor = conn.execute("SELECT * FROM routines WHERE name = ?", (name,))
        row = cursor.fetchone()
        if not row:
            print(f"Routine '{name}' not found.")
            return
    
    print(f"Triggering routine '{name}' immediately...")
    scheduler = RoutinesScheduler()
    scheduler._run_job_wrapper(dict(row), datetime.datetime.now())
    print("Execution complete.")

def view_logs(name, limit=10):
    init_db()
    with get_db_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM routine_logs WHERE routine_name = ? ORDER BY triggered_at DESC LIMIT ?",
            (name, limit)
        )
        rows = cursor.fetchall()
        if not rows:
            print(f"No logs found for routine '{name}'.")
            return
        
        for r in rows:
            trig = r["triggered_at"][:19].replace("T", " ")
            fin = r["finished_at"][:19].replace("T", " ") if r["finished_at"] else "N/A"
            print(f"Log ID: {r['id']} | Triggered: {trig} | Finished: {fin} | Status: {r['status']}")
            if r["output"]:
                print(f"--- Output ---\n{r['output'].strip()}")
            if r["error"]:
                print(f"--- Error ---\n{r['error'].strip()}")
            print("=" * 40)

def print_help():
    print("""Routines CLI Management tool

Usage:
  python routines.py list
  python routines.py add <name> <schedule> <type> <action> [--timeout N]
  python routines.py delete <name>
  python routines.py pause <name>
  python routines.py resume <name>
  python routines.py trigger <name>
  python routines.py logs <name> [--limit N]
  python routines.py daemon

Arguments:
  schedule: Cron expression (e.g. "*/5 * * * *") or interval (e.g. "10s", "5m")
  type:     "shell" or "prompt"
  action:   The CLI command or prompt text to run
  --timeout: Optional timeout in seconds (default 300)
  --limit:   Optional number of logs to show (default 10)
""")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print_help()
        sys.exit(1)
        
    cmd = sys.argv[1].lower()
    
    if cmd == "list":
        list_routines()
    elif cmd == "add":
        if len(sys.argv) < 6:
            print("Error: Missing arguments for 'add'")
            print_help()
            sys.exit(1)
        name = sys.argv[2]
        sched = sys.argv[3]
        t_name = sys.argv[4]
        act = sys.argv[5]
        
        timeout = 300
        if "--timeout" in sys.argv:
            idx = sys.argv.index("--timeout")
            if idx + 1 < len(sys.argv):
                timeout = int(sys.argv[idx + 1])
                
        add_routine(name, sched, t_name, act, timeout)
    elif cmd == "delete":
        if len(sys.argv) < 3:
            print("Error: Missing routine name")
            sys.exit(1)
        delete_routine(sys.argv[2])
    elif cmd == "pause":
        if len(sys.argv) < 3:
            print("Error: Missing routine name")
            sys.exit(1)
        pause_routine(sys.argv[2])
    elif cmd == "resume":
        if len(sys.argv) < 3:
            print("Error: Missing routine name")
            sys.exit(1)
        resume_routine(sys.argv[2])
    elif cmd == "trigger":
        if len(sys.argv) < 3:
            print("Error: Missing routine name")
            sys.exit(1)
        trigger_routine(sys.argv[2])
    elif cmd == "logs":
        if len(sys.argv) < 3:
            print("Error: Missing routine name")
            sys.exit(1)
        name = sys.argv[2]
        limit = 10
        if "--limit" in sys.argv:
            idx = sys.argv.index("--limit")
            if idx + 1 < len(sys.argv):
                limit = int(sys.argv[idx + 1])
        view_logs(name, limit)
    elif cmd == "daemon":
        print("Starting Routines Scheduler Daemon...")
        scheduler = RoutinesScheduler()
        scheduler.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down daemon...")
            scheduler.stop()
    else:
        print(f"Unknown command '{cmd}'")
        print_help()
        sys.exit(1)
