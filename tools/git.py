import subprocess
import shutil
import os
from registry import tool

def is_git_installed():
    return shutil.which("git") is not None

def is_inside_work_tree():
    try:
        res = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], capture_output=True, text=True, check=False)
        return res.stdout.strip() == "true"
    except Exception:
        return False

@tool
def git_status():
    """Get the current state of the git repository (modified files, untracked files)."""
    if not is_git_installed():
        return "Error: git executable is not installed or not in PATH."
    if not is_inside_work_tree():
        return "Error: Current directory is not a git repository."
    try:
        res = subprocess.run(["git", "status", "-s"], capture_output=True, text=True, check=False)
        if res.returncode != 0:
            return f"Error executing git status: {res.stderr}"
        return res.stdout if res.stdout.strip() else "Clean working directory (nothing modified)."
    except Exception as e:
        return f"Error running git status: {e}"

@tool
def git_diff(file_path: str = ""):
    """Show changes made to files in the repository. Optionally specify a file path."""
    if not is_git_installed():
        return "Error: git executable is not installed or not in PATH."
    if not is_inside_work_tree():
        return "Error: Current directory is not a git repository."
    try:
        cmd = ["git", "diff"]
        if file_path:
            cmd.append(file_path)
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode != 0:
            return f"Error executing git diff: {res.stderr}"
        return res.stdout if res.stdout.strip() else "No diff found."
    except Exception as e:
        return f"Error running git diff: {e}"

@tool
def git_add(files: str):
    """Stage modified or new files to git index. Set files to '.' to add all changes."""
    if not is_git_installed():
        return "Error: git executable is not installed or not in PATH."
    if not is_inside_work_tree():
        return "Error: Current directory is not a git repository."
    try:
        res = subprocess.run(["git", "add", files], capture_output=True, text=True, check=False)
        if res.returncode != 0:
            return f"Error adding files to git: {res.stderr}"
        return f"Successfully added '{files}' to git staging area."
    except Exception as e:
        return f"Error running git add: {e}"

@tool
def git_commit(message: str):
    """Commit staged changes to the repository with a commit message."""
    if not is_git_installed():
        return "Error: git executable is not installed or not in PATH."
    if not is_inside_work_tree():
        return "Error: Current directory is not a git repository."
    try:
        res = subprocess.run(["git", "commit", "-m", message], capture_output=True, text=True, check=False)
        if res.returncode != 0:
            return f"Error committing changes: {res.stderr}"
        return f"Successfully committed changes:\n{res.stdout}"
    except Exception as e:
        return f"Error running git commit: {e}"

@tool
def git_log(count: int = 10):
    """View recent commits in git history. Defaults to showing last 10 commits."""
    if not is_git_installed():
        return "Error: git executable is not installed or not in PATH."
    if not is_inside_work_tree():
        return "Error: Current directory is not a git repository."
    try:
        res = subprocess.run(["git", "log", "-n", str(count), "--oneline"], capture_output=True, text=True, check=False)
        if res.returncode != 0:
            return f"Error retrieving git log: {res.stderr}"
        return res.stdout if res.stdout.strip() else "No commits found in repository history."
    except Exception as e:
        return f"Error running git log: {e}"

@tool
def git_checkout(branch_or_file: str):
    """Checkout a branch or restore files from git index."""
    if not is_git_installed():
        return "Error: git executable is not installed or not in PATH."
    if not is_inside_work_tree():
        return "Error: Current directory is not a git repository."
    try:
        res = subprocess.run(["git", "checkout", branch_or_file], capture_output=True, text=True, check=False)
        if res.returncode != 0:
            return f"Error checking out / restoring '{branch_or_file}': {res.stderr}"
        return f"Successfully checked out / restored '{branch_or_file}'.\n{res.stdout}"
    except Exception as e:
        return f"Error running git checkout: {e}"
