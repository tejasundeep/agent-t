"""
artifacts.py — Planning & progress-tracking tools for multi-step tasks.

Files written to <project_root>/artifacts/:
  implementation_plan.md  — full plan: objective, tools, approach
  tasks.md                — live checklist: tracks step status for resumption
"""

import json
import datetime
import pathlib
from registry import tool

_ARTIFACTS = pathlib.Path(__file__).parent.parent / "artifacts"
_PLAN_FILE  = _ARTIFACTS / "implementation_plan.md"
_TASKS_FILE = _ARTIFACTS / "tasks.md"

_STATUS_MARKER = {
    "pending":     " ",
    "in_progress": "/",
    "done":        "x",
    "failed":      "!",
}


def _now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _ensure_artifacts_dir():
    _ARTIFACTS.mkdir(exist_ok=True)


# ──────────────────────────────────────────────
# Tool: create_plan
# ──────────────────────────────────────────────
@tool
def create_plan(title: str, overview: str, steps: str):
    """Create a multi-step execution plan before starting a complex task.
    ALWAYS call this first whenever a task requires more than one tool call.

    Args:
        title    : Short name for the task (e.g. "Audit Python files").
        overview : One-paragraph description of the objective and approach.
        steps    : JSON array of step objects. Each object must have:
                   - "description": what this step does (str)
                   - "tool": the exact tool name that will be called (str)
                   Example: [{"description": "List workspace files", "tool": "list_dir"},
                              {"description": "Count lines", "tool": "shell"}]

    Creates two files in artifacts/:
        implementation_plan.md  — full plan reference
        tasks.md                — live progress checklist
    """
    _ensure_artifacts_dir()

    try:
        steps_list = json.loads(steps)
        if not isinstance(steps_list, list) or not steps_list:
            return "Error: 'steps' must be a non-empty JSON array."
    except Exception as e:
        return f"Error parsing steps JSON: {e}"

    ts = _now()

    # ── implementation_plan.md ──────────────────
    plan_lines = [
        f"# Plan: {title}",
        f"**Created:** {ts}",
        "",
        "## Objective",
        overview,
        "",
        "## Execution Steps",
    ]
    for i, step in enumerate(steps_list, 1):
        tool_name = step.get("tool", "?")
        desc      = step.get("description", "")
        plan_lines.append(f"{i}. **`{tool_name}`** — {desc}")

    plan_lines += ["", "## Notes", "*(Agent appends observations here during execution.)*", ""]
    _PLAN_FILE.write_text("\n".join(plan_lines), encoding="utf-8")

    # ── tasks.md ────────────────────────────────
    task_lines = [
        f"# Tasks: {title}",
        f"**Started:** {ts}",
        "**Status:** in_progress",
        "",
        "## Checklist",
        "",
    ]
    for i, step in enumerate(steps_list, 1):
        desc      = step.get("description", "")
        tool_name = step.get("tool", "?")
        task_lines.append(f"- [ ] **Step {i}** (`{tool_name}`): {desc}")

    task_lines += ["", f"**Last Updated:** {ts}"]
    _TASKS_FILE.write_text("\n".join(task_lines), encoding="utf-8")

    return (
        f"Plan '{title}' created with {len(steps_list)} steps.\n"
        f"  → artifacts/implementation_plan.md\n"
        f"  → artifacts/tasks.md"
    )


# ──────────────────────────────────────────────
# Tool: update_task
# ──────────────────────────────────────────────
@tool
def update_task(step_number: int, status: str):
    """Update the status of a step in tasks.md during execution.

    Call with status='in_progress' when a step begins,
    then 'done' or 'failed' when it finishes.

    Args:
        step_number : 1-indexed step number matching the plan.
        status      : One of 'pending' | 'in_progress' | 'done' | 'failed'.

    Checkbox legend in tasks.md:
        [ ] = pending   [/] = in_progress   [x] = done   [!] = failed
    """
    if not _TASKS_FILE.exists():
        return "Error: No tasks.md found. Call create_plan first."

    marker = _STATUS_MARKER.get(status)
    if marker is None:
        return f"Error: Invalid status '{status}'. Use: pending | in_progress | done | failed."

    content = _TASKS_FILE.read_text(encoding="utf-8")
    lines   = content.splitlines()

    target  = f"**Step {step_number}**"
    updated = False
    for i, line in enumerate(lines):
        if target in line and line.lstrip().startswith("- ["):
            # Replace only the checkbox bracket content
            rest     = line[line.index("]") + 1:]
            lines[i] = f"- [{marker}]{rest}"
            updated  = True
            break

    if not updated:
        return f"Error: Step {step_number} not found in tasks.md."

    ts = _now()

    # Refresh Last Updated timestamp
    for i, line in enumerate(lines):
        if line.startswith("**Last Updated:**"):
            lines[i] = f"**Last Updated:** {ts}"
            break

    # Auto-mark overall Status when all steps are terminal
    step_lines = [l for l in lines if l.lstrip().startswith("- [")]
    if step_lines and all(l[l.index("[")+1] in ("x", "!") for l in step_lines):
        has_fail = any(l[l.index("[")+1] == "!" for l in step_lines)
        new_status = "completed_with_errors" if has_fail else "completed"
        for i, line in enumerate(lines):
            if line.startswith("**Status:**"):
                lines[i] = f"**Status:** {new_status}"
                break

    _TASKS_FILE.write_text("\n".join(lines), encoding="utf-8")
    return f"Step {step_number} → {status}."


# ──────────────────────────────────────────────
# Tool: add_plan_note
# ──────────────────────────────────────────────
@tool
def add_plan_note(note: str):
    """Append an observation or finding to the Notes section of implementation_plan.md.
    Use this to record important discoveries, errors encountered, or decisions made mid-task.

    Args:
        note : The text to append (plain string, markdown supported).
    """
    if not _PLAN_FILE.exists():
        return "Error: No implementation_plan.md found. Call create_plan first."

    content = _PLAN_FILE.read_text(encoding="utf-8")
    ts      = _now()
    entry   = f"\n- [{ts}] {note}"

    # Insert before the last blank line / end of file, after ## Notes
    if "## Notes" in content:
        content = content.rstrip() + entry + "\n"
    else:
        content += f"\n## Notes{entry}\n"

    _PLAN_FILE.write_text(content, encoding="utf-8")
    return f"Note appended to implementation_plan.md."


# ──────────────────────────────────────────────
# Tool: read_plan
# ──────────────────────────────────────────────
@tool
def read_plan():
    """Read the current implementation_plan.md and tasks.md.
    Use this to review the plan mid-task or to understand what has already been done.
    """
    parts = []

    if _PLAN_FILE.exists():
        parts.append("=== implementation_plan.md ===\n" + _PLAN_FILE.read_text(encoding="utf-8"))
    else:
        parts.append("No implementation_plan.md found.")

    if _TASKS_FILE.exists():
        parts.append("=== tasks.md ===\n" + _TASKS_FILE.read_text(encoding="utf-8"))
    else:
        parts.append("No tasks.md found.")

    return "\n\n".join(parts)


# ──────────────────────────────────────────────
# Tool: check_resume
# ──────────────────────────────────────────────
@tool
def check_resume():
    """Check whether an incomplete multi-step task exists and can be resumed.
    Call this at session start when the user asks to resume a previous task,
    or when a task was interrupted.

    Returns the full plan + current task progress if an unfinished plan is found,
    or a 'nothing to resume' message otherwise.
    """
    if not _TASKS_FILE.exists():
        return "No previous task found in artifacts/."

    content = _TASKS_FILE.read_text(encoding="utf-8")
    status_line = next(
        (l for l in content.splitlines() if l.startswith("**Status:**")), ""
    )
    if "completed" in status_line:
        return f"Previous task is already {status_line.replace('**Status:**', '').strip()}. Nothing to resume."

    plan_text = _PLAN_FILE.read_text(encoding="utf-8") if _PLAN_FILE.exists() else "Plan file missing."
    return (
        "⚠ Incomplete task found. Resuming from last checkpoint.\n\n"
        f"=== implementation_plan.md ===\n{plan_text}\n\n"
        f"=== tasks.md ===\n{content}"
    )
