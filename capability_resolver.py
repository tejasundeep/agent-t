"""Module to resolve required capabilities from user prompts and filter tool schemas."""
import re

# Broad capabilities mapped to keywords and associated tool name pattern matching rules
RULES = [
    {
        "name": "filesystem",
        "keywords": [
            r"file", r"dir", r"folder", r"read", r"write", r"path", r"delete", r"copy", r"move",
            r"create", r"patch", r"list", r"find", r"grep", r"txt", r"py", r"json", r"md", r"csv"
        ],
        "tool_patterns": [r"file", r"dir", r"list", r"grep", r"patch"]
    },
    {
        "name": "terminal",
        "keywords": [
            r"terminal", r"cmd", r"bash", r"powershell", r"run", r"execute", r"command",
            r"shell", r"process"
        ],
        "tool_patterns": [r"shell", r"command", r"run", r"process", r"exec"]
    },
    {
        "name": "git",
        "keywords": [
            r"git", r"commit", r"push", r"pull", r"branch", r"merge", r"clone", r"status",
            r"diff", r"repo"
        ],
        "tool_patterns": [r"git"]
    },
    {
        "name": "search",
        "keywords": [r"search", r"google", r"query", r"lookup", r"find", r"web", r"bing"],
        "tool_patterns": [r"search", r"web", r"fetch", r"google"]
    },
    {
        "name": "database",
        "keywords": [
            r"db", r"database", r"sql", r"sqlite", r"query", r"select", r"insert", r"table"
        ],
        "tool_patterns": [r"db", r"sql", r"database"]
    },
    {
        "name": "time",
        "keywords": [r"time", r"date", r"now", r"clock", r"calendar"],
        "tool_patterns": [r"time", r"date", r"now"]
    }
]

def resolve_tools(prompt: str, all_tool_schemas: list) -> list:
    """
    Dynamically filters tool schemas based on the keywords matched in the user's prompt.
    If no specific capability matched, returns all tool schemas as a fallback.
    """
    prompt_lower = prompt.lower()
    matched_patterns = set()

    for rule in RULES:
        # Check if any keyword matches the prompt with word boundaries
        if any(re.search(r"\b" + kw + r"\b", prompt_lower) for kw in rule["keywords"]):
            matched_patterns.update(rule["tool_patterns"])

    # If no patterns matched, return all tool schemas (no-waste fallback)
    if not matched_patterns:
        return all_tool_schemas

    filtered_schemas = []
    for schema in all_tool_schemas:
        name = schema["function"]["name"].lower()
        # If the tool name matches any of our resolved patterns, include it
        if any(re.search(pat, name) for pat in matched_patterns):
            filtered_schemas.append(schema)

    # Fallback: if we matched keywords but no registered tools fit the patterns, return all
    if not filtered_schemas:
        return all_tool_schemas

    return filtered_schemas
