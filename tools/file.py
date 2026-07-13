import os
import pathlib
import fnmatch
from registry import tool

@tool
def read_file(path: str, start_line: int = 1, end_line: int = -1):
    """Read contents of a text file with optional line-range (1-indexed). Set end_line to -1 for end of file."""
    p = pathlib.Path(path).resolve()
    if not p.is_file():
        return f"Error: File '{path}' does not exist."
    try:
        content = p.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines(keepends=True)
        # Handle 1-indexed range
        start = max(1, start_line) - 1
        if end_line == -1 or end_line >= len(lines):
            sliced = lines[start:]
        else:
            end = min(len(lines), end_line)
            sliced = lines[start:end]
        return "".join(sliced)
    except Exception as e:
        return f"Error reading file '{path}': {e}"

@tool
def write_file(path: str, content: str):
    """Write/overwrite full contents of a file. Automatically creates parent directories if missing."""
    p = pathlib.Path(path).resolve()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Successfully wrote to '{path}' ({len(content)} characters)."
    except Exception as e:
        return f"Error writing to file '{path}': {e}"

@tool
def patch_file(path: str, search_text: str, replace_text: str):
    """Perform a search-and-replace modification on a file. Finds search_text and replaces it with replace_text."""
    p = pathlib.Path(path).resolve()
    if not p.is_file():
        return f"Error: File '{path}' does not exist."
    try:
        content = p.read_text(encoding="utf-8", errors="replace")
        norm_content = content.replace("\r\n", "\n")
        norm_search = search_text.replace("\r\n", "\n")
        norm_replace = replace_text.replace("\r\n", "\n")

        if norm_search not in norm_content:
            return f"Error: Search text not found in '{path}'."
        
        occurrences = norm_content.count(norm_search)
        if occurrences > 1:
            return f"Error: Search text found {occurrences} times in '{path}'. Be more specific to ensure a unique match."

        new_content = norm_content.replace(norm_search, norm_replace, 1)
        
        if "\r\n" in content and "\r\n" not in new_content:
            new_content = new_content.replace("\n", "\r\n")

        p.write_text(new_content, encoding="utf-8")
        return f"Successfully patched '{path}' (replaced 1 occurrence)."
    except Exception as e:
        return f"Error patching file '{path}': {e}"

@tool
def list_dir(path: str = "."):
    """List directory contents including files and subdirectories with sizes/types."""
    p = pathlib.Path(path).resolve()
    if not p.is_dir():
        return f"Error: Directory '{path}' does not exist."
    try:
        results = []
        for entry in os.scandir(p):
            info = {
                "name": entry.name,
                "type": "directory" if entry.is_dir() else "file",
                "size_bytes": entry.stat().st_size if entry.is_file() else 0
            }
            results.append(info)
        results.sort(key=lambda x: (x["type"] != "directory", x["name"].lower()))
        output = [f"Contents of {p}:"]
        for r in results:
            type_char = "[D]" if r["type"] == "directory" else "[F]"
            size_str = f" ({r['size_bytes']} bytes)" if r["type"] == "file" else ""
            output.append(f"  {type_char} {r['name']}{size_str}")
        return "\n".join(output)
    except Exception as e:
        return f"Error listing directory '{path}': {e}"

@tool
def find_files(directory: str = ".", pattern: str = "*"):
    """Find files matching a glob pattern recursively within a directory."""
    dir_path = pathlib.Path(directory).resolve()
    if not dir_path.is_dir():
        return f"Error: Directory '{directory}' does not exist."
    try:
        matched_files = []
        for root, dirs, files in os.walk(dir_path):
            for filename in fnmatch.filter(files, pattern):
                full_path = pathlib.Path(root) / filename
                rel_path = full_path.relative_to(dir_path)
                matched_files.append(str(rel_path))
        if not matched_files:
            return f"No files matching '{pattern}' in '{directory}'."
        matched_files.sort()
        return f"Found {len(matched_files)} files matching '{pattern}':\n" + "\n".join(matched_files[:100])
    except Exception as e:
        return f"Error finding files: {e}"

@tool
def grep_search(pattern: str, directory: str = "."):
    """Search for text pattern in files (case-insensitive plain text search)."""
    dir_path = pathlib.Path(directory).resolve()
    if not dir_path.is_dir():
        return f"Error: Directory '{directory}' does not exist."
    try:
        matches = []
        exclude_dirs = {".git", "__pycache__", "venv", ".venv", ".accio"}
        for root, dirs, files in os.walk(dir_path):
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            for file in files:
                file_path = pathlib.Path(root) / file
                try:
                    if file_path.stat().st_size > 1024 * 1024:
                        continue
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                    if not content:
                        continue
                    lines = content.splitlines()
                    for idx, line in enumerate(lines, 1):
                        if pattern.lower() in line.lower():
                            rel_path = file_path.relative_to(dir_path)
                            matches.append(f"{rel_path}:{idx}: {line.strip()}")
                except Exception:
                    continue
        if not matches:
            return f"No matches found for '{pattern}'."
        return f"Found {len(matches)} matches:\n" + "\n".join(matches[:50])
    except Exception as e:
        return f"Error during grep search: {e}"

@tool
def delete_file(path: str):
    """Delete a file from the filesystem."""
    p = pathlib.Path(path).resolve()
    if not p.is_file():
        return f"Error: File '{path}' does not exist."
    try:
        p.unlink()
        return f"Successfully deleted file '{path}'."
    except Exception as e:
        return f"Error deleting file '{path}': {e}"

@tool
def make_directory(path: str):
    """Create a new directory (and any parent directories) if they do not exist."""
    p = pathlib.Path(path).resolve()
    try:
        p.mkdir(parents=True, exist_ok=True)
        return f"Successfully created directory '{path}'."
    except Exception as e:
        return f"Error creating directory '{path}': {e}"

@tool
def move_file(source: str, destination: str):
    """Move or rename a file/directory from source to destination."""
    src = pathlib.Path(source).resolve()
    dst = pathlib.Path(destination).resolve()
    if not src.exists():
        return f"Error: Source '{source}' does not exist."
    try:
        # Create parent directory for destination if it doesn't exist
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return f"Successfully moved '{source}' to '{destination}'."
    except Exception as e:
        return f"Error moving '{source}' to '{destination}': {e}"

@tool
def file_info(path: str):
    """Retrieve detailed metadata about a file (size, creation/modification time, permissions)."""
    p = pathlib.Path(path).resolve()
    if not p.exists():
        return f"Error: Path '{path}' does not exist."
    try:
        import datetime
        stat = p.stat()
        mtime = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        ctime = datetime.datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M:%S")
        
        info = [
            f"Path: {p}",
            f"Type: {'Directory' if p.is_dir() else 'File'}",
            f"Size: {stat.st_size} bytes",
            f"Last Modified: {mtime}",
            f"Created: {ctime}",
            f"Readable: {os.access(p, os.R_OK)}",
            f"Writable: {os.access(p, os.W_OK)}",
            f"Executable: {os.access(p, os.X_OK)}"
        ]
        return "\n".join(info)
    except Exception as e:
        return f"Error fetching metadata for '{path}': {e}"

@tool
def file_hash(path: str, algorithm: str = "sha256"):
    """Compute the cryptographic hash (checksum) of a file. Supported algorithms: md5, sha1, sha256."""
    p = pathlib.Path(path).resolve()
    if not p.is_file():
        return f"Error: File '{path}' does not exist or is a directory."
    import hashlib
    algo = algorithm.lower()
    if algo not in ["md5", "sha1", "sha256"]:
        return f"Error: Unsupported hash algorithm '{algorithm}'. Choose from: md5, sha1, sha256."
    try:
        h = hashlib.new(algo)
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return f"{algo.upper()}: {h.hexdigest()}"
    except Exception as e:
        return f"Error hashing file '{path}': {e}"

@tool
def file_diff(path_a: str, path_b: str):
    """Generate a unified line-by-line diff between two arbitrary text files."""
    pa = pathlib.Path(path_a).resolve()
    pb = pathlib.Path(path_b).resolve()
    if not pa.is_file():
        return f"Error: File '{path_a}' does not exist."
    if not pb.is_file():
        return f"Error: File '{path_b}' does not exist."
    try:
        import difflib
        lines_a = pa.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        lines_b = pb.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        diff = difflib.unified_diff(
            lines_a, lines_b,
            fromfile=str(pa), tofile=str(pb)
        )
        return "".join(diff) or "No differences found."
    except Exception as e:
        return f"Error generating diff: {e}"

@tool
def bulk_replace(pattern: str, replacement: str, directory: str = "."):
    """Search and replace a text string recursively across all matching files in a directory.
    Useful for codebase-wide refactoring.
    """
    dir_path = pathlib.Path(directory).resolve()
    if not dir_path.is_dir():
        return f"Error: Directory '{directory}' does not exist."
    try:
        modified_files = []
        exclude_dirs = {".git", "__pycache__", "venv", ".venv", ".accio"}
        for root, dirs, files in os.walk(dir_path):
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            for file in files:
                file_path = pathlib.Path(root) / file
                try:
                    if file_path.stat().st_size > 1024 * 1024:  # > 1MB
                        continue
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                    if pattern in content:
                        new_content = content.replace(pattern, replacement)
                        file_path.write_text(new_content, encoding="utf-8")
                        modified_files.append(str(file_path.relative_to(dir_path)))
                except Exception:
                    continue
        if not modified_files:
            return f"No occurrences of '{pattern}' were found to replace."
        return f"Successfully replaced '{pattern}' with '{replacement}' in {len(modified_files)} files:\n" + "\n".join(modified_files)
    except Exception as e:
        return f"Error during bulk replace: {e}"
