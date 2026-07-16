import ast
import difflib
import importlib
import importlib.util
import pathlib
import re
import subprocess
import sys
import traceback
from registry import tool

# Names that would overwrite Python internals or agent-t core modules
_RESERVED_NAMES = {
    "__init__", "__main__", "registry", "agent", "config", "app",
    "main", "llm", "context_engine", "pipeline_engine", "routines",
    "concurrency", "message", "toolset_distributions", "utils",
}

# Standard library top-level modules — never pip-install these
_STDLIB_MODULES = set(sys.stdlib_module_names) if hasattr(sys, "stdlib_module_names") else {
    "os", "sys", "re", "json", "math", "time", "datetime", "pathlib", "shutil",
    "subprocess", "threading", "io", "ast", "importlib", "traceback", "hashlib",
    "base64", "urllib", "http", "socket", "struct", "collections", "itertools",
    "functools", "typing", "abc", "copy", "random", "string", "textwrap",
    "logging", "unittest", "csv", "sqlite3", "zipfile", "tarfile", "gzip",
    "tempfile", "glob", "fnmatch", "stat", "platform", "getpass", "uuid",
}


def _extract_imports(code: str) -> list[str]:
    """Parse code AST and return a list of top-level module names being imported."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []  # syntax errors are caught separately

    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.append(node.module.split(".")[0])
    return list(set(modules))


def _check_and_install_deps(modules: list[str]) -> tuple[bool, str]:
    """Check each module. Install via pip if missing.
    Returns (all_ok: bool, report: str).
    """
    missing = []
    for mod in modules:
        # Skip stdlib and internal agent-t modules
        if mod in _STDLIB_MODULES or mod in _RESERVED_NAMES or mod == "registry":
            continue
        if importlib.util.find_spec(mod) is None:
            missing.append(mod)

    if not missing:
        return True, "All dependencies already satisfied."

    lines = [f"Missing packages detected: {missing}. Installing..."]
    for pkg in missing:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", pkg],
                capture_output=True, text=True, timeout=120
            )
            if result.returncode == 0:
                lines.append(f"  ✓ Installed '{pkg}' successfully.")
            else:
                lines.append(f"  ✗ Failed to install '{pkg}':\n{result.stderr.strip()}")
                return False, "\n".join(lines)
        except subprocess.TimeoutExpired:
            lines.append(f"  ✗ pip install '{pkg}' timed out after 120s.")
            return False, "\n".join(lines)
        except Exception as e:
            lines.append(f"  ✗ Unexpected error installing '{pkg}': {e}")
            return False, "\n".join(lines)

    return True, "\n".join(lines)


@tool
def read_tool_source(name: str) -> str:
    """Read the source code of an existing on-demand tool by name.
    Use this before upgrading a tool so you can see what it currently does
    and write an expanded version that preserves existing behaviour.
    Returns the full source code string, or an error if the tool does not exist.
    """
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', name):
        return f"Invalid tool name '{name}'."
    tools_dir = pathlib.Path(__file__).parent
    file_path = tools_dir / f"{name}.py"
    if not file_path.exists():
        return f"Tool '{name}' does not exist on disk. It may be a built-in tool (not upgradeable)."
    return file_path.read_text(encoding="utf-8")


@tool
def create_tool(name: str, code: str) -> str:
    """Dynamically compiles, writes, and registers a new tool function.
    Automatically checks and installs missing Python dependencies before writing any code.
    The code MUST define a function decorated with @tool (imported from registry).
    Example:
        from registry import tool
        @tool
        def my_tool(arg: str):
            \"\"\"Does something useful.\"\"\"
            return "Result: " + arg
    """
    # Step 0a: Name format validation
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', name):
        return (
            f"Invalid tool name '{name}'. "
            "Must be a valid Python identifier (letters, digits, underscores; cannot start with a digit)."
        )
    if name in _RESERVED_NAMES:
        return (
            f"Forbidden tool name '{name}'. "
            "That name is reserved by the agent-t core. Choose a different name."
        )

    # Step 0b: Similarity guard — hard-block duplicate or near-duplicate tool creation.
    # Scan all existing on-demand tools (.py files in tools/) for close name matches.
    tools_dir = pathlib.Path(__file__).parent
    existing_tool_names = [
        p.stem for p in tools_dir.glob("*.py")
        if p.stem not in _RESERVED_NAMES and not p.stem.endswith(".bak")
    ]

    # Exact match on disk → must upgrade, not recreate
    if name in existing_tool_names:
        return (
            f"BLOCKED: Tool '{name}' already exists on disk.\n"
            f"Do NOT create a duplicate. Use upgrade_tool('{name}', upgraded_code) instead.\n"
            f"Call read_tool_source('{name}') first to read the current implementation."
        )

    # Near-match → surface the closest existing tool and block creation
    close_matches = difflib.get_close_matches(name, existing_tool_names, n=3, cutoff=0.7)
    if close_matches:
        matches_str = ", ".join(f"'{m}'" for m in close_matches)
        return (
            f"BLOCKED: Tool name '{name}' is too similar to existing tool(s): {matches_str}.\n"
            f"Do NOT create a near-duplicate. Upgrade the existing tool instead:\n"
            f"  1. Call read_tool_source('{close_matches[0]}') to inspect it.\n"
            f"  2. Call upgrade_tool('{close_matches[0]}', upgraded_code) to expand its capabilities."
        )

    # Step 1: Syntax check — catch errors before touching disk or network
    try:
        compile(code, f"<tool:{name}>", "exec")
    except SyntaxError:
        return f"Syntax Error — code was not written to disk:\n{traceback.format_exc()}"

    # Step 2: Extract all imports from AST and ensure dependencies are installed
    required_modules = _extract_imports(code)
    ok, dep_report = _check_and_install_deps(required_modules)
    if not ok:
        return f"Dependency Installation Failed — code was not written to disk.\n{dep_report}"

    # Step 3: All deps satisfied — write file to disk
    file_path = tools_dir / f"{name}.py"
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(code)
    except OSError as e:
        return f"File Write Error: {e}"

    # Step 4: Import/reload module so @tool decorator fires and registers the tool
    try:
        module_name = f"tools.{name}"
        if module_name in sys.modules:
            importlib.reload(sys.modules[module_name])
        else:
            importlib.import_module(module_name)
    except Exception:
        # If import fails, clean up the written file to avoid orphaned broken files
        try:
            file_path.unlink(missing_ok=True)
        except OSError:
            pass
        return (
            f"Import Error — the file was removed to keep the tools/ folder clean.\n"
            f"{traceback.format_exc()}"
        )

    return (
        f"Tool '{name}' created and registered successfully.\n"
        f"Dependency report:\n{dep_report}"
    )


@tool
def upgrade_tool(name: str, upgraded_code: str) -> str:
    """Upgrade an existing on-demand tool with expanded capabilities.
    Use this when a user request is a near-match for an existing tool but the tool
    needs new parameters, logic, or library support to fully cover the task.
    Workflow:
      1. Call read_tool_source(name) to inspect the current implementation.
      2. Write upgraded_code that preserves all existing behaviour AND adds the new capability.
      3. Call upgrade_tool(name, upgraded_code) — it backs up the original, validates,
         installs new deps, overwrites, and hot-reloads the tool live.
    Only upgrades tools that exist on disk (on-demand tools). Built-in tools cannot be upgraded.
    """
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', name):
        return f"Invalid tool name '{name}'."
    if name in _RESERVED_NAMES:
        return f"'{name}' is a reserved core module and cannot be upgraded."

    tools_dir = pathlib.Path(__file__).parent
    file_path = tools_dir / f"{name}.py"
    backup_path = tools_dir / f"{name}.bak.py"

    if not file_path.exists():
        return (
            f"Tool '{name}' does not exist on disk. "
            f"Use create_tool to create it first."
        )

    # Step 1: Syntax check before touching anything
    try:
        compile(upgraded_code, f"<upgrade:{name}>", "exec")
    except SyntaxError:
        return f"Syntax Error in upgraded code — original tool untouched:\n{traceback.format_exc()}"

    # Step 2: Install any new dependencies introduced by the upgrade
    required_modules = _extract_imports(upgraded_code)
    ok, dep_report = _check_and_install_deps(required_modules)
    if not ok:
        return f"Dependency Installation Failed — original tool untouched.\n{dep_report}"

    # Step 3: Backup original before overwriting
    try:
        backup_path.write_text(file_path.read_text(encoding="utf-8"), encoding="utf-8")
    except OSError as e:
        return f"Backup Error — original tool untouched: {e}"

    # Step 4: Write upgraded code
    try:
        file_path.write_text(upgraded_code, encoding="utf-8")
    except OSError as e:
        return f"File Write Error — original tool untouched: {e}"

    # Step 5: Hot-reload so the registry picks up the upgraded version immediately
    try:
        module_name = f"tools.{name}"
        if module_name in sys.modules:
            importlib.reload(sys.modules[module_name])
        else:
            importlib.import_module(module_name)
    except Exception:
        # Restore from backup if reload fails
        try:
            file_path.write_text(backup_path.read_text(encoding="utf-8"), encoding="utf-8")
            module_name = f"tools.{name}"
            if module_name in sys.modules:
                importlib.reload(sys.modules[module_name])
        except Exception:
            pass
        return (
            f"Import Error after upgrade — original tool restored from backup.\n"
            f"{traceback.format_exc()}"
        )

    return (
        f"Tool '{name}' upgraded and reloaded successfully.\n"
        f"Backup saved at: {backup_path}\n"
        f"Dependency report:\n{dep_report}"
    )
