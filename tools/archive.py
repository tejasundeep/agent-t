import zipfile
import pathlib
import os
from registry import tool

@tool
def archive_files(archive_path: str, files_to_add: str):
    """Compress multiple files or a directory into a .zip archive.
    files_to_add parameter can be a single file path, folder path, or comma-separated list of paths.
    """
    arc = pathlib.Path(archive_path).resolve()
    try:
        arc.parent.mkdir(parents=True, exist_ok=True)
        paths = [p.strip() for p in files_to_add.split(",") if p.strip()]
        
        with zipfile.ZipFile(arc, "w", zipfile.ZIP_DEFLATED) as zipf:
            for p_str in paths:
                p = pathlib.Path(p_str).resolve()
                if not p.exists():
                    return f"Error: Path '{p_str}' does not exist."
                
                if p.is_file():
                    zipf.write(p, p.name)
                elif p.is_dir():
                    # Walk directory
                    for root, dirs, files in os.walk(p):
                        for file in files:
                            filePath = pathlib.Path(root) / file
                            relPath = filePath.relative_to(p.parent)
                            zipf.write(filePath, relPath)
        return f"Successfully created zip archive at '{archive_path}'."
    except Exception as e:
        return f"Error creating archive: {e}"

@tool
def extract_archive(archive_path: str, dest_dir: str):
    """Decompress a .zip archive into the specified destination directory."""
    arc = pathlib.Path(archive_path).resolve()
    dst = pathlib.Path(dest_dir).resolve()
    if not arc.is_file():
        return f"Error: Archive file '{archive_path}' does not exist."
    try:
        dst.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(arc, "r") as zipf:
            zipf.extractall(dst)
        return f"Successfully extracted archive to '{dest_dir}'."
    except Exception as e:
        return f"Error extracting archive: {e}"
