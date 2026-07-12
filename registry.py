import importlib
import inspect
import pkgutil
import pathlib

class Registry:
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
            if param.default is inspect._empty:
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

    def run(self, name, args):
        return self.tools[name](**args)

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
