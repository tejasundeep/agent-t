import time
import eventlet
eventlet.monkey_patch()

import os
import json
import subprocess
import shutil
import threading
import sqlite3
import datetime
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
from routines import get_db_connection, init_db, calculate_next_run

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
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# Ensure a workspace directory exists in the project
WORKSPACE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'workspace')
if not os.path.exists(WORKSPACE_DIR):
    os.makedirs(WORKSPACE_DIR)

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
            return res
        except Exception as e:
            if sid:
                socketio.emit('step_log', {'id': step_id, 'log': f"Tool Error: {str(e)}"}, room=sid)
                socketio.emit('step_complete', {'id': step_id, 'status': 'error'}, room=sid)
            raise e
    
    registry.run = custom_run

def run_actual_agent(sid, prompt):
    thread_name = threading.current_thread().name
    current_step_sid[thread_name] = sid
    
    try:
        agent = Agent(SYSTEM_PROMPT)
        # Attempt to stream from real agent
        socketio.emit('trajectory_log', {'log': "[System 1 Decomposing]: Projecting target states with AST context..."}, room=sid)
        time.sleep(0.5)
        
        # Stream response
        for chunk in agent.stream(prompt):
            socketio.emit('thought_chunk', {'text': chunk}, room=sid)
            
    except Exception as e:
        # Fallback to local simulation when LM Studio / LLM is offline
        socketio.emit('trajectory_log', {'log': f"[Warning]: LLM Daemon Offline ({str(e)}). Running fallback execution..."}, room=sid)
        time.sleep(0.5)
        simulate_runner_steps(sid, prompt)
    finally:
        socketio.emit('agent_status', {'status': 'finished'}, room=sid)
        if thread_name in current_step_sid:
            del current_step_sid[thread_name]

def simulate_runner_steps(sid, prompt):
    prompt_lower = prompt.lower()
    
    # Send AST states similar to screenshot
    socketio.emit('trajectory_log', {'log': f"[System 1 Decomposing]: Projecting target states with AST context for: '{prompt}'"}, room=sid)
    time.sleep(0.6)
    socketio.emit('trajectory_log', {'log': "[Trajectory Plan]: Projected 2 states: analyze_request, execute_workspace_update"}, room=sid)
    time.sleep(0.6)
    socketio.emit('trajectory_log', {'log': "[Executing Step 1]: Target: analyze_request - Parse prompt intent and identify files."}, room=sid)
    time.sleep(0.4)
    
    # 1. Thought for 1s
    socketio.emit('thought_start', {'duration': 1}, room=sid)
    time.sleep(1.0)
    
    # 2. Read file step
    step1_id = "step1"
    socketio.emit('step_start', {
        'id': step1_id,
        'action': 'read_file',
        'name': 'Read orchestrator.py #L130-179',
        'details': 'Reading backend controller configuration'
    }, room=sid)
    time.sleep(0.3)
    socketio.emit('step_log', {'id': step1_id, 'log': "Opening file orchestrator.py...\nReading lines 130 to 179..."}, room=sid)
    time.sleep(0.4)
    socketio.emit('step_complete', {'id': step1_id, 'status': 'success'}, room=sid)
    
    # 3. Thought for 2s
    socketio.emit('thought_start', {'duration': 2}, room=sid)
    time.sleep(2.0)
    
    # 4. Diff / Write step
    step2_id = "step2"
    socketio.emit('step_start', {
        'id': step2_id,
        'action': 'replace_file_content',
        'name': 'Update orchestrator.py',
        'details': 'Applying code optimization'
    }, room=sid)
    time.sleep(0.3)
    
    # Stream git diff lines
    diff_lines = [
        "Applying patch to orchestrator.py...",
        "--- orchestrator.py",
        "+++ orchestrator.py",
        "@@ -135,2 +135,2 @@",
        "- * To fetch URLs or APIs, use Custom Plugin \"http_client\" or tool \"http_request\".",
        "+ * To fetch URLs or APIs, use Custom Plugin \"http_client\" or tool \"http_request\". Do NOT use \"shell_exec\""
    ]
    for line in diff_lines:
        socketio.emit('step_log', {'id': step2_id, 'log': line}, room=sid)
        time.sleep(0.2)
        
    socketio.emit('step_complete', {'id': step2_id, 'status': 'success'}, room=sid)
    
    # 5. Thought for 1s
    socketio.emit('thought_start', {'duration': 1}, room=sid)
    time.sleep(1.0)
    
    # Send final response text chunk
    for char in f"Successfully processed workspace update for prompt: {prompt}.":
        socketio.emit('thought_chunk', {'text': char}, room=sid)
        time.sleep(0.01)

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('start_agent')
def handle_start_agent(data):
    prompt = data.get('prompt', '').strip()
    threading.Thread(target=run_actual_agent, args=(request.sid, prompt)).start()

@app.route('/api/reset', methods=['POST'])
def reset_workspace():
    try:
        # Create some starter files in workspace
        config_path = os.path.join(WORKSPACE_DIR, 'orchestrator.py')
        with open(config_path, 'w') as f:
            f.write("# orchestrator.py\n# Main system control routines\n")
        return {"status": "success", "message": "Workspace reset complete."}
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

if __name__ == '__main__':
    socketio.run(app, host='127.0.0.1', port=5000, debug=True)
