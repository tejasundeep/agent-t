"""Tool Registry module for dynamic tool discovery, schema parsing, and execution serialization."""
import importlib
import inspect
import pkgutil
import pathlib
import sys
import threading
import time as _time

class Registry:
    """Registry that holds tool definitions, schemas, and handles execution/serialization/scopes."""
    def __init__(self):
        self.tools = {}
        self.schema = []
        self.interpreter_scopes = {}       # session_key -> scope dict
        self._scope_timestamps = {}        # session_key -> last_used epoch (for TTL cleanup)
        self._SCOPE_TTL_SECONDS = 7200     # 2 hours — evict idle scopes
        self._MAX_SCOPES = 64              # hard cap to prevent unbounded growth
        self.pending_inputs = {}           # thread_name -> event entry for interactive prompts
        self._thread_to_session = {}       # thread_name -> sid (web) or thread_name (CLI)

    # ── Session/Thread mapping ────────────────────────────────────────────────

    def register_thread_session(self, thread_name: str, sid: str):
        """Map a worker thread to a specific socket session ID for scope isolation."""
        self._thread_to_session[thread_name] = sid

    def unregister_thread_session(self, thread_name: str):
        """Remove thread→session mapping after agent run completes."""
        self._thread_to_session.pop(thread_name, None)

    def _session_key_for_thread(self, thread_name: str) -> str:
        """Resolve the stable session key for the current thread.
        Web mode: returns the socket sid (stable per browser tab).
        CLI mode: returns the thread name (only one user, acceptable).
        """
        return self._thread_to_session.get(thread_name, thread_name)

    # ── Scope management ─────────────────────────────────────────────────────

    def _evict_stale_scopes(self):
        """Remove scopes that have not been used within TTL, and enforce hard cap."""
        now = _time.monotonic()
        stale = [k for k, ts in self._scope_timestamps.items()
                 if now - ts > self._SCOPE_TTL_SECONDS]
        for k in stale:
            self.interpreter_scopes.pop(k, None)
            self._scope_timestamps.pop(k, None)

        # If still over cap, evict oldest by timestamp
        while len(self.interpreter_scopes) > self._MAX_SCOPES:
            oldest = min(self._scope_timestamps, key=self._scope_timestamps.get)
            self.interpreter_scopes.pop(oldest, None)
            self._scope_timestamps.pop(oldest, None)

    def get_interpreter_scope(self, thread_name: str) -> dict:
        """Retrieve or create a persistent execution scope, keyed by stable session ID."""
        self._evict_stale_scopes()
        session_key = self._session_key_for_thread(thread_name)

        if session_key not in self.interpreter_scopes:
            scope = {}
            def ask_user(prompt: str) -> str:
                return self.request_input(thread_name, prompt)
            scope["ask_user"] = ask_user
            scope["os"]   = __import__("os")
            scope["sys"]  = __import__("sys")
            scope["json"] = __import__("json")
            self.interpreter_scopes[session_key] = scope

        self._scope_timestamps[session_key] = _time.monotonic()
        return self.interpreter_scopes[session_key]

    def clear_scope(self, thread_name: str):
        """Explicitly wipe the scope for a session (e.g. on reset)."""
        session_key = self._session_key_for_thread(thread_name)
        self.interpreter_scopes.pop(session_key, None)
        self._scope_timestamps.pop(session_key, None)

    # ── Interactive input ─────────────────────────────────────────────────────

    def request_input(self, thread_name: str, prompt: str) -> str:
        """Block execution until input arrives from CLI or Socket.IO.
        Raises TimeoutError after 120 seconds to prevent frozen threads.
        """
        if thread_name not in self.pending_inputs:
            # CLI fallback — write directly to real stdout, bypassing any StringIO redirect
            sys.__stdout__.write(f"\n{prompt}")
            sys.__stdout__.flush()
            return sys.__stdin__.readline().strip()

        # Web mode: signal the frontend and block until response arrives
        entry = self.pending_inputs[thread_name]
        entry["prompt"] = prompt
        entry["event"].clear()
        entry["response"] = None
        entry["ready"] = True

        # FIX Issue 1: hard timeout prevents permanently frozen worker threads
        acquired = entry["event"].wait(timeout=120)
        entry["ready"] = False
        if not acquired:
            raise TimeoutError(
                f"ask_user() timed out after 120s waiting for user input: '{prompt}'"
            )
        return entry["response"] or ""

    def provide_input(self, thread_name: str, val: str):
        """Unblock a waiting ask_user() call by providing the user's response."""
        if thread_name in self.pending_inputs:
            entry = self.pending_inputs[thread_name]
            entry["response"] = val
            entry["event"].set()

    # ── Tool decorator ────────────────────────────────────────────────────────

    def tool(self, f):
        """Decorator that registers a function as a tool and updates the JSON schema."""
        type_map = {
            str: "string",
            int: "integer",
            float: "number",
            bool: "boolean",
            list: "array",
            dict: "object",
        }
        sig = inspect.signature(f)
        props = {}
        required = []
        for name, param in sig.parameters.items():
            props[name] = {"type": type_map.get(param.annotation, "string")}
            if param.default is inspect.Parameter.empty:
                required.append(name)
        # De-duplicate on reload: remove existing entry for this name before re-adding
        self.schema = [
            item for item in self.schema
            if not (item["type"] == "function" and item["function"]["name"] == f.__name__)
        ]
        self.schema.append({
            "type": "function",
            "function": {
                "name": f.__name__,
                "description": inspect.getdoc(f) or "",
                "parameters": {"type": "object", "properties": props, "required": required},
            },
        })
        self.tools[f.__name__] = f
        return f

    # ── Serialization & execution ─────────────────────────────────────────────

    def serialize_output(self, _tool_name, val):
        """Serializes complex tool outputs into human-readable markdown formats."""
        if val is None:
            return "None"
        if isinstance(val, (str, int, float, bool)):
            return str(val)
        if isinstance(val, (list, tuple)):
            if not val:
                return "Empty list"
            if all(isinstance(item, dict) for item in val):
                keys = list(val[0].keys())
                header    = "| " + " | ".join(keys) + " |"
                separator = "| " + " | ".join(["---"] * len(keys)) + " |"
                rows = [
                    "| " + " | ".join(str(item.get(k, "")) for k in keys) + " |"
                    for item in val
                ]
                return "\n".join([header, separator] + rows)
            return "\n".join(f"- {str(x)}" for x in val)
        if isinstance(val, dict):
            if not val:
                return "Empty object"
            return "\n".join(f"* **{k}**: {v}" for k, v in val.items())
        return str(val)

    def run(self, name, args):
        """Runs the registered tool with arguments, serializing output or catching errors."""
        try:
            raw_result = self.tools[name](**args)
            return self.serialize_output(name, raw_result)
        except Exception as e:  # pylint: disable=broad-exception-caught
            return f"Error executing tool '{name}': {e}"

    def load_tools(self, package_path: str = "tools"):
        """Dynamically import all modules in the `tools` package so their @tool decorators run."""
        pkg_dir = pathlib.Path(__file__).parent / package_path
        if not pkg_dir.is_dir():
            return
        for _, mod_name, is_pkg in pkgutil.iter_modules([str(pkg_dir)]):
            if is_pkg:
                continue
            importlib.import_module(f"{package_path}.{mod_name}")

# Global registry instance
registry = Registry()
# Convenience decorator alias
tool = registry.tool
# Register all tool modules automatically
registry.load_tools()
