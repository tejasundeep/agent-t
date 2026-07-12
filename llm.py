from openai import OpenAI

client = OpenAI(base_url="http://localhost:1234/v1", api_key="lm-studio")
MODEL = "bjivanovich/qwen3.5-4b-vision"


def chat(messages, tools=None):
    if tools is None:
        return client.chat.completions.create(
            model=MODEL, messages=messages, stream=True
        )
    return client.chat.completions.create(
        model=MODEL, messages=messages, tools=tools, tool_choice="auto", stream=True
    )


def stream(resp):
    text = ""
    calls = {}
    for ch in resp:
        d = ch.choices[0].delta
        if d.content:
            # print(d.content, end="", flush=True)
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
