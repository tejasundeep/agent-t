"""Tool Registry module for dynamic tool discovery, schema parsing, and execution serialization."""
import importlib
import inspect
import pkgutil
import pathlib

class Registry:
    """Registry that holds tool definitions, schemas, and handles execution/serialization."""
    def __init__(self):
        self.tools = {}
        self.schema = []

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
        # Append tool description to the schema
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

    def serialize_output(self, _tool_name, val):
        """Serializes complex tool outputs into human-readable markdown formats."""
        if val is None:
            return "None"
        if isinstance(val, (str, int, float, bool)):
            return str(val)
        if isinstance(val, (list, tuple)):
            if not val:
                return "Empty list"
            # If it's a list of dicts, format as a markdown table
            if all(isinstance(item, dict) for item in val):
                keys = list(val[0].keys())
                header = "| " + " | ".join(keys) + " |"
                separator = "| " + " | ".join(["---"] * len(keys)) + " |"
                rows = []
                for item in val:
                    row = "| " + " | ".join(str(item.get(k, "")) for k in keys) + " |"
                    rows.append(row)
                return "\n".join([header, separator] + rows)
            # Otherwise format as bullet points
            return "\n".join(f"- {str(x)}" for x in val)
        if isinstance(val, dict):
            if not val:
                return "Empty object"
            # Format as key-value bullet points
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
