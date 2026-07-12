import json
from llm import chat,stream
from registry import registry
class Agent:
    def __init__(self,system=None):
        self.messages=[{"role":"system","content":system}] if system else []
    def __call__(self,prompt):
        self.messages.append({"role":"user","content":prompt})
        while True:
            text,calls=stream(chat(self.messages,registry.schema))
            if not calls:
                self.messages.append({"role":"assistant","content":text});return text
            self.messages.append({"role":"assistant","tool_calls":[{"id":c["id"],"type":"function","function":{"name":c["name"],"arguments":c["args"]}} for c in calls]})
            for c in calls:
                try:r=registry.run(c["name"],json.loads(c["args"] or "{}"))
                except Exception as e:r=f"Tool Error: {e}"
                self.messages.append({"role":"tool","tool_call_id":c["id"],"content":str(r)})
