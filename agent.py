import json
from llm import chat,stream
from registry import registry
from context_engine import ContextEngine

class Agent:
    def __init__(self,system=None):
        self.messages=[{"role":"system","content":system}] if system else []
        self.context_engine = ContextEngine()

    def __call__(self,prompt):
        """Legacy call returning full response string (kept for compatibility)."""
        self.messages.append({"role":"user","content":prompt})
        while True:
            optimized_messages = self.context_engine.assemble_context(self.messages)
            text,calls=stream(chat(optimized_messages,registry.schema))
            if not calls:
                self.messages.append({"role":"assistant","content":text})
                self.context_engine.buffer_interaction(prompt, text)
                return text
            self.messages.append({"role":"assistant","tool_calls":[{"id":c["id"],"type":"function","function":{"name":c["name"],"arguments":c["args"]}} for c in calls]})
            for c in calls:
                try:
                    r=registry.run(c["name"],json.loads(c["args"] or "{}"))
                except Exception as e:
                    r=f"Tool Error: {e}"
                self.messages.append({"role":"tool","tool_call_id":c["id"],"content":str(r)})

    def stream(self, prompt):
        """Yield assistant response characters as they arrive.
        The LLM client may return the full response in a single delta. To simulate
        a live typing effect we emit each character individually with a short pause.
        Tool calls are collected and processed after the entire text has been streamed.
        """
        import time
        self.messages.append({"role": "user", "content": prompt})
        while True:
            full_text = ""
            tool_calls = []
            optimized_messages = self.context_engine.assemble_context(self.messages)
            full_text, tool_calls = stream(chat(optimized_messages, registry.schema))
            # Stream the assistant's response character by character for a live typing effect
            for char in full_text:
                yield char
                time.sleep(0.02)
            # Append the full assistant response to the message list
            self.messages.append({"role": "assistant", "content": full_text})
            # If there are tool calls, process them after the response is fully streamed
            if tool_calls:
                self.messages[-1]["tool_calls"] = [{"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": c["args"]}} for c in tool_calls]
                for c in tool_calls:
                    try:
                        r = registry.run(c["name"], json.loads(c["args"] or "{}"))
                    except Exception as e:
                        r = f"Tool Error: {e}"
                    self.messages.append({"role": "tool", "tool_call_id": c["id"], "content": str(r)})
            else:
                self.context_engine.buffer_interaction(prompt, full_text)
                break

