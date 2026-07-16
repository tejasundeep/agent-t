"""Agent execution module.

Handles prompt processing, capability-based tool filtering, single-turn response
template parsing, variable substitution, and output streaming.
"""
import json
import re
import time
from llm import chat, stream
from registry import registry
from context_engine import ContextEngine

def parse_llm_json(text):
    """Tries to find and parse a JSON block in the LLM response text."""
    if not text:
        return None
    # 1. Try finding markdown code block
    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except Exception:  # pylint: disable=broad-exception-caught
            pass
    # 2. Try parsing the whole text
    try:
        return json.loads(text.strip())
    except Exception:  # pylint: disable=broad-exception-caught
        pass
    # 3. Try searching for anything between { and }
    match_braces = re.search(r"({.*})", text, re.DOTALL)
    if match_braces:
        try:
            return json.loads(match_braces.group(1).strip())
        except Exception:  # pylint: disable=broad-exception-caught
            pass
    return None

class Agent:
    """Core Agent class containing standard execution loops and streaming hooks."""
    def __init__(self, system=None):
        self.messages = [{"role": "system", "content": system}] if system else []
        self.context_engine = ContextEngine()

    def __call__(self, prompt):
        """Legacy call returning full response string (kept for compatibility)."""
        self.messages.append({"role": "user", "content": prompt})

        while True:
            optimized_messages = self.context_engine.assemble_context(self.messages)
            # Pass all tools to LLM
            resolved_schema = registry.schema

            text, calls = stream(chat(optimized_messages, resolved_schema))

            # Check for JSON block in the text specifying single_turn template execution
            parsed = parse_llm_json(text)
            if parsed and parsed.get("mode") == "single_turn":
                template = parsed.get("response_template", "")
                json_calls = parsed.get("tool_calls", [])

                variables = {}
                for tc in json_calls:
                    name = tc.get("name")
                    args = tc.get("arguments", {})
                    r = registry.run(name, args)
                    variables[name] = r

                # Dynamic Template injection
                final_response = template
                for name, val in variables.items():
                    final_response = final_response.replace(f"{{{name}}}", str(val))

                self.messages.append({"role": "assistant", "content": final_response})
                self.context_engine.buffer_interaction(prompt, final_response)
                return final_response

            # Fallback to standard OpenAI-style tool execution (multi-turn logic)
            if not calls:
                self.messages.append({"role": "assistant", "content": text})
                self.context_engine.buffer_interaction(prompt, text)
                return text

            formatted_calls = [
                {
                    "id": c["id"],
                    "type": "function",
                    "function": {"name": c["name"], "arguments": c["args"]}
                }
                for c in calls
            ]
            self.messages.append({"role": "assistant", "tool_calls": formatted_calls})

            for c in calls:
                r = registry.run(c["name"], json.loads(c["args"] or "{}"))
                self.messages.append({"role": "tool", "tool_call_id": c["id"], "content": str(r)})

    def stream(self, prompt):
        """Yield assistant response characters.

        Buffers single_turn templates to perform execution and injection before outputting,
        while streaming multi_turn/direct chat instantly.
        """
        self.messages.append({"role": "user", "content": prompt})

        while True:
            optimized_messages = self.context_engine.assemble_context(self.messages)
            # Pass all tools to LLM
            resolved_schema = registry.schema

            # Obtain response text and native tool calls in a single pass
            full_text, tool_calls = stream(chat(optimized_messages, resolved_schema))

            parsed = parse_llm_json(full_text)
            if parsed and parsed.get("mode") == "single_turn":
                # Single-turn template route: Buffer, execute, populate, then stream
                template = parsed.get("response_template", "")
                json_calls = parsed.get("tool_calls", [])

                variables = {}
                for tc in json_calls:
                    name = tc.get("name")
                    args = tc.get("arguments", {})
                    r = registry.run(name, args)
                    variables[name] = r

                final_response = template
                for name, val in variables.items():
                    final_response = final_response.replace(f"{{{name}}}", str(val))

                # Emit the final injected output character by character
                for char in final_response:
                    yield char
                    time.sleep(0.01)

                self.messages.append({"role": "assistant", "content": final_response})
                self.context_engine.buffer_interaction(prompt, final_response)
                break

            # If not a single-turn template, treat as regular streaming or multi-turn execution
            if tool_calls:
                formatted_tc = [
                    {
                        "id": c["id"],
                        "type": "function",
                        "function": {"name": c["name"], "arguments": c["args"]}
                    }
                    for c in tool_calls
                ]
                self.messages.append({
                    "role": "assistant",
                    "content": full_text,
                    "tool_calls": formatted_tc
                })
                for c in tool_calls:
                    r = registry.run(c["name"], json.loads(c["args"] or "{}"))
                    self.messages.append({
                        "role": "tool", "tool_call_id": c["id"], "content": str(r)
                    })
                continue

            # Direct chat response: stream characters immediately
            for char in full_text:
                yield char
                time.sleep(0.01)
            self.messages.append({"role": "assistant", "content": full_text})
            self.context_engine.buffer_interaction(prompt, full_text)
            break
