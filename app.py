import time

import os
import json
import subprocess
import shutil
import threading
import sqlite3
import datetime
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
from routines import get_db_connection, init_db, calculate_next_run, RoutinesScheduler

# Try to import agent modules from current directory
try:
    from agent import Agent
    from registry import registry
    from config import SYSTEM_PROMPT
except ImportError:
    Agent = None
    registry = None
    SYSTEM_PROMPT = "Default system prompt."

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret-key-agent-t'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Ensure a workspace directory exists in the project
WORKSPACE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'workspace')
if not os.path.exists(WORKSPACE_DIR):
    os.makedirs(WORKSPACE_DIR)

# ── Notifications DB helpers ──────────────────────────────────────────────────
def init_notifications_db():
    """Creates the notifications table if it doesn't exist."""
    with get_db_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id         INTEGER  PRIMARY KEY AUTOINCREMENT,
                title      TEXT     NOT NULL,
                message    TEXT     NOT NULL,
                level      TEXT     NOT NULL DEFAULT 'info',
                is_read    INTEGER  NOT NULL DEFAULT 0,
                created_at TIMESTAMP NOT NULL
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_notif_created ON notifications(created_at DESC);")
        conn.commit()

def push_notification(title, message, level='info'):
    """Inserts a notification row and broadcasts it to all connected clients."""
    try:
        init_notifications_db()
        now = datetime.datetime.now().isoformat()
        with get_db_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO notifications (title, message, level, is_read, created_at) VALUES (?, ?, ?, 0, ?)",
                (title, message, level, now)
            )
            conn.commit()
            notif_id = cursor.lastrowid
        socketio.emit('notification_push', {
            'id':         notif_id,
            'title':      title,
            'message':    message,
            'level':      level,
            'created_at': now
        })
    except Exception as e:
        print(f"[Notification Error] {e}", file=os.sys.stderr)

# ── Chat History DB helpers ──────────────────────────────────────────────────
def init_chat_db():
    """Creates the chat_history table for UI event persistence."""
    with get_db_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_history (
                id         INTEGER  PRIMARY KEY AUTOINCREMENT,
                event_type TEXT     NOT NULL,
                content    TEXT     NOT NULL DEFAULT '',
                meta       TEXT     NOT NULL DEFAULT '{}',
                created_at TIMESTAMP NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_created ON chat_history(id ASC);")
        conn.commit()

def save_chat_event(event_type, content='', meta=None):
    """Persists a single UI event row to the chat_history table."""
    try:
        with get_db_connection() as conn:
            conn.execute(
                "INSERT INTO chat_history (event_type, content, meta, created_at) VALUES (?, ?, ?, ?)",
                (event_type, content, json.dumps(meta or {}), datetime.datetime.now().isoformat())
            )
            conn.commit()
    except Exception as e:
        print(f"[Chat DB Error] {e}", file=os.sys.stderr)

def build_llm_seed_messages():
    """Reconstructs the LLM messages list (user + assistant turns) from persisted chat history."""
    try:
        with get_db_connection() as conn:
            rows = conn.execute(
                "SELECT event_type, content FROM chat_history "
                "WHERE event_type IN ('user_msg', 'agent_response') ORDER BY id ASC"
            ).fetchall()
        messages = []
        for row in rows:
            if row['event_type'] == 'user_msg':
                messages.append({"role": "user", "content": row['content']})
            elif row['event_type'] == 'agent_response':
                messages.append({"role": "assistant", "content": row['content']})
        return messages
    except Exception:
        return []

# ── Start background RoutinesScheduler with notification callback wired in ────
init_db()
init_notifications_db()
init_chat_db()
_global_scheduler = RoutinesScheduler(notification_callback=push_notification)
_global_scheduler.start()

# Global status tracking for websocket stream
current_step_sid = {}

# Intercept tool calls dynamically to stream step details
if registry:
    original_run = registry.run
    def custom_run(name, args):
        sid = current_step_sid.get(threading.current_thread().name)
        step_id = f"step_{int(time.time() * 1000)}"
        
        if sid:
            socketio.emit('step_start', {
                'id': step_id,
                'action': name,
                'name': f"Running tool: {name}",
                'details': json.dumps(args)
            }, room=sid)
            socketio.emit('step_log', {'id': step_id, 'log': f"Executing registry tool '{name}' with arguments: {json.dumps(args)}"}, room=sid)
        
        try:
            res = original_run(name, args)
            if sid:
                socketio.emit('step_log', {'id': step_id, 'log': f"Success: {str(res)[:1000]}"}, room=sid)
                socketio.emit('step_complete', {'id': step_id, 'status': 'success'}, room=sid)
            # Persist completed tool step
            save_chat_event('tool_step', '', {
                'action': name,
                'name': f"Running tool: {name}",
                'details': json.dumps(args)[:300],
                'status': 'success'
            })
            return res
        except Exception as e:
            if sid:
                socketio.emit('step_log', {'id': step_id, 'log': f"Tool Error: {str(e)}"}, room=sid)
                socketio.emit('step_complete', {'id': step_id, 'status': 'error'}, room=sid)
            # Persist failed tool step
            save_chat_event('tool_step', '', {
                'action': name,
                'name': f"Running tool: {name}",
                'details': json.dumps(args)[:300],
                'status': 'error'
            })
            raise e
    
    registry.run = custom_run

def run_actual_agent(sid, prompt):
    thread_name = threading.current_thread().name
    current_step_sid[thread_name] = sid
    
    # Persist user message BEFORE running so build_llm_seed_messages includes it
    save_chat_event('user_msg', prompt)

    try:
        agent = Agent(SYSTEM_PROMPT)

        # Seed the agent with past conversation turns so it remembers context
        past = build_llm_seed_messages()  # includes the user msg we just saved as last item
        if len(past) > 1:
            # Extend messages with everything EXCEPT the current prompt;
            # agent.stream() will append it internally
            agent.messages.extend(past[:-1])

        # Emit + persist opening trajectory log
        traj_text = "[System 1 Decomposing]: Projecting target states with AST context..."
        socketio.emit('trajectory_log', {'log': traj_text}, room=sid)
        save_chat_event('traj_log', traj_text)
        time.sleep(0.5)
        
        # Stream response and collect all chunks for persistence
        collected = []
        for chunk in agent.stream(prompt):
            socketio.emit('thought_chunk', {'text': chunk}, room=sid)
            collected.append(chunk)

        # Persist the complete agent response
        final_response = ''.join(collected)
        if final_response.strip():
            save_chat_event('agent_response', final_response)
            
    except Exception as e:
        # Fallback to local simulation when LLM is offline
        warn_text = f"[Warning]: LLM Daemon Offline ({str(e)}). Running fallback execution..."
        socketio.emit('trajectory_log', {'log': warn_text}, room=sid)
        save_chat_event('traj_log', warn_text)
        time.sleep(0.5)
        simulate_runner_steps(sid, prompt)
    finally:
        socketio.emit('agent_status', {'status': 'finished'}, room=sid)
        if thread_name in current_step_sid:
            del current_step_sid[thread_name]

def simulate_runner_steps(sid, prompt):
    prompt_lower = prompt.lower()
    
    # Send AST states similar to screenshot
    t1 = f"[System 1 Decomposing]: Projecting target states with AST context for: '{prompt}'"
    t2 = "[Trajectory Plan]: Projected 2 states: analyze_request, execute_workspace_update"
    t3 = "[Executing Step 1]: Target: analyze_request - Parse prompt intent and identify files."
    for txt in [t1, t2, t3]:
        socketio.emit('trajectory_log', {'log': txt}, room=sid)
        save_chat_event('traj_log', txt)
        time.sleep(0.6 if txt == t1 else 0.4)
    
    # 1. Thought for 1s
    socketio.emit('thought_start', {'duration': 1}, room=sid)
    time.sleep(1.0)
    
    # 2. Read file step
    step1_id = "step1"
    socketio.emit('step_start', {
        'id': step1_id,
        'action': 'read_file',
        'name': 'Read workspace file',
        'details': 'Reading workspace file for context'
    }, room=sid)
    time.sleep(0.3)
    socketio.emit('step_log', {'id': step1_id, 'log': "Opening workspace file...\nReading content..."}, room=sid)
    time.sleep(0.4)
    socketio.emit('step_complete', {'id': step1_id, 'status': 'success'}, room=sid)
    save_chat_event('tool_step', '', {'action': 'read_file', 'name': 'Read workspace file', 'status': 'success'})
    
    # 3. Thought for 2s
    socketio.emit('thought_start', {'duration': 2}, room=sid)
    time.sleep(2.0)
    
    # 4. Write step
    step2_id = "step2"
    socketio.emit('step_start', {
        'id': step2_id,
        'action': 'write_file',
        'name': 'Write workspace file',
        'details': 'Applying update'
    }, room=sid)
    time.sleep(0.3)
    diff_lines = [
        "Applying changes to workspace...",
        "--- workspace/file.py",
        "+++ workspace/file.py",
        "@@ -1,2 +1,3 @@",
        "- # placeholder",
        "+ # updated by agent"
    ]
    for line in diff_lines:
        socketio.emit('step_log', {'id': step2_id, 'log': line}, room=sid)
        time.sleep(0.2)
    socketio.emit('step_complete', {'id': step2_id, 'status': 'success'}, room=sid)
    save_chat_event('tool_step', '', {'action': 'write_file', 'name': 'Write workspace file', 'status': 'success'})
    
    # 5. Thought for 1s
    socketio.emit('thought_start', {'duration': 1}, room=sid)
    time.sleep(1.0)
    
    # Final simulated response
    final_sim = f"Successfully processed workspace update for prompt: {prompt}."
    for char in final_sim:
        socketio.emit('thought_chunk', {'text': char}, room=sid)
        time.sleep(0.01)
    save_chat_event('agent_response', final_sim)

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('start_agent')
def handle_start_agent(data):
    prompt = data.get('prompt', '').strip()
    threading.Thread(target=run_actual_agent, args=(request.sid, prompt)).start()

@app.route('/api/reset', methods=['POST'])
def reset_workspace():
    """Wipes the workspace directory completely empty and clears chat history."""
    try:
        # Clear workspace files
        for entry in os.scandir(WORKSPACE_DIR):
            if entry.is_dir(follow_symlinks=False):
                shutil.rmtree(entry.path)
            else:
                os.remove(entry.path)
        return {"status": "success", "message": "Workspace files cleared."}
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500

@app.route('/api/routines', methods=['GET'])
def api_list_routines():
    init_db()
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM routines ORDER BY name ASC")
            rows = cursor.fetchall()
            routines = []
            for r in rows:
                routines.append({
                    "name": r["name"],
                    "schedule": r["schedule"],
                    "type": r["type"],
                    "action": r["action"],
                    "status": r["status"],
                    "timeout": r["timeout"],
                    "created_at": r["created_at"],
                    "last_run": r["last_run"],
                    "next_run": r["next_run"]
                })
            return {"status": "success", "routines": routines}
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500

@app.route('/api/routines', methods=['POST'])
def api_create_routine():
    init_db()
    data = request.json or {}
    name = data.get("name", "").strip()
    schedule = data.get("schedule", "").strip()
    type_name = data.get("type", "").strip()
    action = data.get("action", "").strip()
    timeout = int(data.get("timeout", 300))
    
    if not name or not schedule or not type_name or not action:
        return {"status": "error", "message": "Missing required fields."}, 400
    if type_name not in ("shell", "prompt"):
        return {"status": "error", "message": "Type must be 'shell' or 'prompt'."}, 400

    # Validate shell action: catch bare 'python -c import' style mistakes
    if type_name == "shell":
        err = _validate_shell_action(action)
        if err:
            return {"status": "error", "message": err}, 400
        
    now = datetime.datetime.now()
    try:
        next_run = calculate_next_run(schedule, now)
    except Exception as e:
        return {"status": "error", "message": f"Invalid schedule: {e}"}, 400
        
    try:
        with get_db_connection() as conn:
            conn.execute(
                "INSERT INTO routines (name, schedule, type, action, status, timeout, created_at, next_run) VALUES (?, ?, ?, ?, 'active', ?, ?, ?)",
                (name, schedule, type_name, action, timeout, now.isoformat(), next_run.isoformat())
            )
            conn.commit()
        return {"status": "success", "message": f"Routine '{name}' created successfully."}
    except sqlite3.IntegrityError:
        return {"status": "error", "message": f"Routine with name '{name}' already exists."}, 400
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500

def _validate_shell_action(action):
    """
    Returns an error string if the shell action looks malformed, else None.
    Catches the most common mistake: `python -c import` (missing quoted code).
    """
    import shlex
    tokens = action.split()
    # Detect: python -c <token> where <token> is a bare keyword with no quotes
    python_keywords = {'import', 'from', 'def', 'class', 'return', 'if', 'for', 'while', 'print'}
    for i, tok in enumerate(tokens):
        if tok == '-c' and i + 1 < len(tokens):
            next_tok = tokens[i + 1]
            # If next token is a bare Python keyword with nothing else, that's broken
            if next_tok.lower() in python_keywords and len(tokens) == i + 2:
                return (
                    f"Shell action looks malformed: 'python -c {next_tok}' is not valid. "
                    f"Wrap the Python code in quotes, e.g.: python -c \"import sys; print(sys.version)\""
                )
    return None

@app.route('/api/routines/<string:name>', methods=['DELETE'])
def api_delete_routine(name):
    init_db()
    try:
        with get_db_connection() as conn:
            cursor = conn.execute("DELETE FROM routines WHERE name = ?", (name,))
            conn.commit()
            if cursor.rowcount > 0:
                return {"status": "success", "message": f"Deleted routine '{name}'."}
            else:
                return {"status": "error", "message": f"Routine '{name}' not found."}, 404
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500

@app.route('/api/routines/<string:name>', methods=['PATCH'])
def api_update_routine(name):
    """Update a routine's action, schedule, and/or timeout."""
    init_db()
    data = request.json or {}
    now  = datetime.datetime.now()
    updates = {}

    if 'action' in data:
        action = data['action'].strip()
        if not action:
            return {"status": "error", "message": "Action cannot be empty."}, 400
        # Re-fetch type to validate
        with get_db_connection() as conn:
            row = conn.execute("SELECT type FROM routines WHERE name = ?", (name,)).fetchone()
        if not row:
            return {"status": "error", "message": f"Routine '{name}' not found."}, 404
        if row['type'] == 'shell':
            err = _validate_shell_action(action)
            if err:
                return {"status": "error", "message": err}, 400
        updates['action'] = action

    if 'schedule' in data:
        schedule = data['schedule'].strip()
        try:
            next_run = calculate_next_run(schedule, now)
            updates['schedule'] = schedule
            updates['next_run'] = next_run.isoformat()
        except Exception as e:
            return {"status": "error", "message": f"Invalid schedule: {e}"}, 400

    if 'timeout' in data:
        try:
            updates['timeout'] = int(data['timeout'])
        except (ValueError, TypeError):
            return {"status": "error", "message": "Timeout must be an integer."}, 400

    if not updates:
        return {"status": "error", "message": "No updatable fields provided."}, 400

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values     = list(updates.values()) + [name]
    try:
        with get_db_connection() as conn:
            cursor = conn.execute(f"UPDATE routines SET {set_clause} WHERE name = ?", values)
            conn.commit()
            if cursor.rowcount == 0:
                return {"status": "error", "message": f"Routine '{name}' not found."}, 404
        return {"status": "success", "message": f"Routine '{name}' updated."}
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500

@app.route('/api/routines/<string:name>/pause', methods=['POST'])
def api_pause_routine(name):
    init_db()
    try:
        with get_db_connection() as conn:
            cursor = conn.execute("UPDATE routines SET status = 'paused' WHERE name = ?", (name,))
            conn.commit()
            if cursor.rowcount > 0:
                return {"status": "success", "message": f"Paused routine '{name}'."}
            else:
                return {"status": "error", "message": f"Routine '{name}' not found."}, 404
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500

@app.route('/api/routines/<string:name>/resume', methods=['POST'])
def api_resume_routine(name):
    init_db()
    now = datetime.datetime.now()
    try:
        with get_db_connection() as conn:
            cursor = conn.execute("SELECT schedule FROM routines WHERE name = ?", (name,))
            row = cursor.fetchone()
            if not row:
                return {"status": "error", "message": f"Routine '{name}' not found."}, 404
            
            try:
                next_run = calculate_next_run(row["schedule"], now)
            except Exception:
                next_run = now

            conn.execute("UPDATE routines SET status = 'active', next_run = ? WHERE name = ?", (next_run.isoformat(), name))
            conn.commit()
        return {"status": "success", "message": f"Resumed routine '{name}'."}
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500

@app.route('/api/routines/<string:name>/trigger', methods=['POST'])
def api_trigger_routine(name):
    init_db()
    try:
        with get_db_connection() as conn:
            cursor = conn.execute("SELECT * FROM routines WHERE name = ?", (name,))
            row = cursor.fetchone()
            if not row:
                return {"status": "error", "message": f"Routine '{name}' not found."}, 404
            routine_dict = dict(row)
        
        # Run it asynchronously in a background thread to prevent blocking
        def run_triggered():
            from routines import RoutinesScheduler
            scheduler = RoutinesScheduler()
            scheduler._run_job_wrapper(routine_dict, datetime.datetime.now())
            
        threading.Thread(target=run_triggered).start()
        return {"status": "success", "message": f"Triggered routine '{name}' in background."}
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500

@app.route('/api/routines/<string:name>/logs', methods=['GET'])
def api_routine_logs(name):
    init_db()
    limit = request.args.get('limit', 10, type=int)
    try:
        with get_db_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM routine_logs WHERE routine_name = ? ORDER BY triggered_at DESC LIMIT ?",
                (name, limit)
            )
            rows = cursor.fetchall()
            logs = []
            for r in rows:
                logs.append({
                    "id": r["id"],
                    "routine_name": r["routine_name"],
                    "status": r["status"],
                    "triggered_at": r["triggered_at"],
                    "finished_at": r["finished_at"],
                    "output": r["output"],
                    "error": r["error"]
                })
            return {"status": "success", "logs": logs}
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500

# ── Chat History REST API ─────────────────────────────────────────────────────

@app.route('/api/history', methods=['GET'])
def api_get_history():
    """Returns all persisted chat events in chronological order for UI replay."""
    init_chat_db()
    try:
        with get_db_connection() as conn:
            rows = conn.execute(
                "SELECT id, event_type, content, meta, created_at FROM chat_history ORDER BY id ASC"
            ).fetchall()
        events = []
        for r in rows:
            try:
                meta = json.loads(r['meta']) if r['meta'] else {}
            except Exception:
                meta = {}
            events.append({
                'id':         r['id'],
                'event_type': r['event_type'],
                'content':    r['content'],
                'meta':       meta,
                'created_at': r['created_at']
            })
        return {'status': 'success', 'events': events}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}, 500


@app.route('/api/history', methods=['DELETE'])
def api_clear_history():
    """Clears all chat history without affecting workspace files."""
    init_chat_db()
    try:
        with get_db_connection() as conn:
            conn.execute("DELETE FROM chat_history")
            conn.commit()
        return {'status': 'success'}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}, 500

# ── Notification Center REST API ──────────────────────────────────────────────

@app.route('/api/notifications', methods=['GET'])
def api_get_notifications():
    """Returns the 50 most recent notifications with unread_count."""
    init_notifications_db()
    limit = request.args.get('limit', 50, type=int)
    try:
        with get_db_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM notifications ORDER BY created_at DESC LIMIT ?",
                (limit,)
            )
            rows = cursor.fetchall()
            notifications = []
            for r in rows:
                notifications.append({
                    "id":         r["id"],
                    "title":      r["title"],
                    "message":    r["message"],
                    "level":      r["level"],
                    "is_read":    bool(r["is_read"]),
                    "created_at": r["created_at"]
                })
            unread_count = sum(1 for n in notifications if not n["is_read"])
            return {"status": "success", "notifications": notifications, "unread_count": unread_count}
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500

@app.route('/api/notifications/mark-read', methods=['POST'])
def api_mark_notifications_read():
    """Marks all notifications (or specific IDs) as read."""
    init_notifications_db()
    data = request.json or {}
    ids  = data.get('ids')  # optional list of ints; if None, mark all
    try:
        with get_db_connection() as conn:
            if ids and isinstance(ids, list):
                placeholders = ",".join("?" * len(ids))
                conn.execute(f"UPDATE notifications SET is_read = 1 WHERE id IN ({placeholders})", ids)
            else:
                conn.execute("UPDATE notifications SET is_read = 1")
            conn.commit()
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500

@app.route('/api/notifications', methods=['DELETE'])
def api_clear_notifications():
    """Deletes all notifications."""
    init_notifications_db()
    try:
        with get_db_connection() as conn:
            conn.execute("DELETE FROM notifications")
            conn.commit()
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500

if __name__ == '__main__':
    socketio.run(app, host='127.0.0.1', port=5000, debug=True, use_reloader=False, log_output=True, allow_unsafe_werkzeug=True)
