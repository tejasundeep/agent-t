import base64
import os
from openai import OpenAI

client = OpenAI(base_url="http://localhost:1234/v1", api_key="lm-studio")
MODEL = "bjivanovich/qwen3.5-4b-vision"

def preprocess_messages(messages):
    screenshot_path = "screenshot.png"
    if not os.path.exists(screenshot_path):
        return messages

    # Determine if we should attach the screenshot
    should_attach = False
    
    # 1. Check if a screenshot tool was invoked or referenced in messages
    for msg in messages:
        if msg.get("role") == "assistant" and "tool_calls" in msg:
            for tc in msg["tool_calls"]:
                if tc.get("function", {}).get("name") == "take_screenshot":
                    should_attach = True
                    break
        if msg.get("role") == "tool" and "screenshot.png" in str(msg.get("content")):
            should_attach = True

    # 2. Check if user prompt references screenshot/screen/desktop
    last_user_content = ""
    for msg in reversed(messages):
        if msg["role"] == "user":
            content = msg["content"]
            if isinstance(content, str):
                last_user_content = content.lower()
            elif isinstance(content, list):
                for item in content:
                    if item.get("type") == "text":
                        last_user_content = item.get("text", "").lower()
            break

    keywords = ["screenshot", "screen", "desktop", "see", "look", "whats on", "read this", "view"]
    if any(kw in last_user_content for kw in keywords):
        should_attach = True

    if not should_attach:
        return messages

    try:
        with open(screenshot_path, "rb") as f:
            img_base64 = base64.b64encode(f.read()).decode("utf-8")
        
        # Attach the image to the last user message
        new_messages = []
        attached = False
        for msg in reversed(messages):
            if msg["role"] == "user" and not attached:
                original_content = msg["content"]
                if isinstance(original_content, list):
                    # Check if already has image
                    has_image = any(item.get("type") == "image_url" for item in original_content)
                    if has_image:
                        new_messages.append(msg)
                    else:
                        new_content = original_content + [
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{img_base64}"}
                            }
                        ]
                        new_messages.append({"role": "user", "content": new_content})
                else:
                    new_messages.append({
                        "role": "user",
                        "content": [
                            {"type": "text", "text": str(original_content)},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{img_base64}"}
                            }
                        ]
                    })
                attached = True
            else:
                new_messages.append(msg)
        return list(reversed(new_messages))
    except Exception as e:
        print(f"[Vision Error] Failed to attach image: {e}")
        return messages

def chat(messages, tools=None):
    processed = preprocess_messages(messages)
    if tools is None:
        return client.chat.completions.create(
            model=MODEL, messages=processed, stream=True
        )
    return client.chat.completions.create(
        model=MODEL, messages=processed, tools=tools, tool_choice="auto", stream=True
    )


def stream(resp):
    text = ""
    calls = {}
    for ch in resp:
        d = ch.choices[0].delta
        if d.content:
            text += d.content
        for tc in d.tool_calls or []:
            c = calls.setdefault(tc.index, {"id": "", "name": "", "args": ""})
            if tc.id:
                c["id"] = tc.id
            if tc.function:
                if tc.function.name:
                    c["name"] = tc.function.name
                if tc.function.arguments:
                    c["args"] += tc.function.arguments
    print()
    return text, list(calls.values())

