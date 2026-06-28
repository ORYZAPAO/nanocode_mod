#!/usr/bin/env python3
"""nanocode - minimal claude code alternative"""

import glob as globlib, json, os, re, subprocess, urllib.request

OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENAI_KEY = os.environ.get("OPENAI_API_KEY")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY")

if OPENROUTER_KEY:
    API_URL = "https://openrouter.ai/api/v1/chat/completions"
    API_KEY = OPENROUTER_KEY
    DEFAULT_MODEL = "anthropic/claude-opus-4.5"
    PROVIDER = "OpenRouter"
    USE_OPENAI = True
elif OPENAI_KEY:
    API_URL = "https://api.openai.com/v1/chat/completions"
    API_KEY = OPENAI_KEY
    DEFAULT_MODEL = "gpt-4o"
    PROVIDER = "OpenAI"
    USE_OPENAI = True
else:
    API_URL = "https://api.anthropic.com/v1/messages"
    API_KEY = ANTHROPIC_KEY or ""
    DEFAULT_MODEL = "claude-opus-4-5"
    PROVIDER = "Anthropic"
    USE_OPENAI = False

MODEL = os.environ.get("MODEL", DEFAULT_MODEL)

RESET, BOLD, DIM = "\033[0m", "\033[1m", "\033[2m"
BLUE, CYAN, GREEN, YELLOW, RED = (
    "\033[34m", "\033[36m", "\033[32m", "\033[33m", "\033[31m",
)


# --- ツール実装 ---


def read(args):
    lines = open(args["path"]).readlines()
    offset = args.get("offset", 0)
    limit = args.get("limit", len(lines))
    selected = lines[offset : offset + limit]
    return "".join(f"{offset + idx + 1:4}| {line}" for idx, line in enumerate(selected))


def write(args):
    with open(args["path"], "w") as f:
        f.write(args["content"])
    return "ok"


def edit(args):
    text = open(args["path"]).read()
    old, new = args["old"], args["new"]
    if old not in text:
        return "error: old_string not found"
    count = text.count(old)
    if not args.get("all") and count > 1:
        return f"error: old_string appears {count} times, must be unique (use all=true)"
    replacement = (
        text.replace(old, new) if args.get("all") else text.replace(old, new, 1)
    )
    with open(args["path"], "w") as f:
        f.write(replacement)
    return "ok"


def glob(args):
    pattern = (args.get("path", ".") + "/" + args["pat"]).replace("//", "/")
    files = globlib.glob(pattern, recursive=True)
    files = sorted(
        files,
        key=lambda f: os.path.getmtime(f) if os.path.isfile(f) else 0,
        reverse=True,
    )
    return "\n".join(files) or "none"


def grep(args):
    pattern = re.compile(args["pat"])
    hits = []
    for filepath in globlib.glob(args.get("path", ".") + "/**", recursive=True):
        try:
            for line_num, line in enumerate(open(filepath), 1):
                if pattern.search(line):
                    hits.append(f"{filepath}:{line_num}:{line.rstrip()}")
        except Exception:
            pass
    return "\n".join(hits[:50]) or "none"


def bash(args):
    proc = subprocess.Popen(
        args["cmd"], shell=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True
    )
    output_lines = []
    try:
        while True:
            line = proc.stdout.readline()
            if not line and proc.poll() is not None:
                break
            if line:
                print(f"  {DIM}│ {line.rstrip()}{RESET}", flush=True)
                output_lines.append(line)
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        output_lines.append("\n(timed out after 30s)")
    return "".join(output_lines).strip() or "(empty)"


# --- ツール定義: (説明, スキーマ, 関数) ---

TOOLS = {
    "read": (
        "Read file with line numbers (file path, not directory)",
        {"path": "string", "offset": "number?", "limit": "number?"},
        read,
    ),
    "write": (
        "Write content to file",
        {"path": "string", "content": "string"},
        write,
    ),
    "edit": (
        "Replace old with new in file (old must be unique unless all=true)",
        {"path": "string", "old": "string", "new": "string", "all": "boolean?"},
        edit,
    ),
    "glob": (
        "Find files by pattern, sorted by mtime",
        {"pat": "string", "path": "string?"},
        glob,
    ),
    "grep": (
        "Search files for regex pattern",
        {"pat": "string", "path": "string?"},
        grep,
    ),
    "bash": (
        "Run shell command",
        {"cmd": "string"},
        bash,
    ),
}


def run_tool(name, args):
    try:
        return TOOLS[name][2](args)
    except Exception as err:
        return f"error: {err}"


def _param_schemas():
    result = []
    for name, (description, params, _fn) in TOOLS.items():
        properties = {}
        required = []
        for param_name, param_type in params.items():
            is_optional = param_type.endswith("?")
            base_type = param_type.rstrip("?")
            properties[param_name] = {
                "type": "integer" if base_type == "number" else base_type
            }
            if not is_optional:
                required.append(param_name)
        schema = {"type": "object", "properties": properties, "required": required}
        result.append((name, description, schema))
    return result


def make_schema():
    schemas = _param_schemas()
    if USE_OPENAI:
        # OpenAI互換: {"type": "function", "function": {...}}
        return [
            {"type": "function", "function": {"name": n, "description": d, "parameters": s}}
            for n, d, s in schemas
        ]
    # Anthropicネイティブ: {"name": ..., "input_schema": {...}}
    return [{"name": n, "description": d, "input_schema": s} for n, d, s in schemas]


def call_api(messages, system_prompt):
    if USE_OPENAI:
        body = {
            "model": MODEL,
            "max_tokens": 8192,
            "messages": [{"role": "system", "content": system_prompt}] + messages,
            "tools": make_schema(),
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        }
    else:
        body = {
            "model": MODEL,
            "max_tokens": 8192,
            "system": system_prompt,
            "messages": messages,
            "tools": make_schema(),
        }
        headers = {
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
            "x-api-key": API_KEY,
        }
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode(),
        headers=headers,
    )
    response = urllib.request.urlopen(request)
    return json.loads(response.read())


def separator():
    return f"{DIM}{'─' * min(os.get_terminal_size().columns, 80)}{RESET}"


def render_markdown(text):
    return re.sub(r"\*\*(.+?)\*\*", f"{BOLD}\\1{RESET}", text)


def _result_preview(result):
    lines = result.split("\n")
    preview = lines[0][:60]
    if len(lines) > 1:
        preview += f" ... +{len(lines) - 1} lines"
    elif len(lines[0]) > 60:
        preview += "..."
    return preview


def main():
    print(f"{BOLD}nanocode{RESET} | {DIM}{MODEL} ({PROVIDER}) | {os.getcwd()}{RESET}\n")
    messages = []
    system_prompt = f"Concise coding assistant. cwd: {os.getcwd()}"

    while True:
        try:
            print(separator())
            user_input = input(f"{BOLD}{BLUE}❯{RESET} ").strip()
            print(separator())
            if not user_input:
                continue
            if user_input in ("/q", "exit"):
                break
            if user_input == "/c":
                messages = []
                print(f"{GREEN}⏺ Cleared conversation{RESET}")
                continue

            messages.append({"role": "user", "content": user_input})

            while True:
                response = call_api(messages, system_prompt)

                if USE_OPENAI:
                    msg = response["choices"][0]["message"]
                    text = msg.get("content") or ""
                    tool_calls = msg.get("tool_calls") or []

                    if text:
                        print(f"\n{CYAN}⏺{RESET} {render_markdown(text)}")

                    assistant_msg = {"role": "assistant", "content": text}
                    if tool_calls:
                        assistant_msg["tool_calls"] = tool_calls
                    messages.append(assistant_msg)

                    if not tool_calls:
                        break

                    for tc in tool_calls:
                        tool_name = tc["function"]["name"]
                        tool_args = json.loads(tc["function"]["arguments"])
                        arg_preview = str(next(iter(tool_args.values()), ""))[:50]
                        print(f"\n{GREEN}⏺ {tool_name.capitalize()}{RESET}({DIM}{arg_preview}{RESET})")

                        result = run_tool(tool_name, tool_args)
                        print(f"  {DIM}⎿  {_result_preview(result)}{RESET}")

                        # OpenAIはtool resultを独立したrole: "tool"メッセージで渡す
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": result,
                        })

                else:  # Anthropicネイティブ
                    content_blocks = response.get("content", [])
                    tool_results = []

                    for block in content_blocks:
                        if block["type"] == "text":
                            print(f"\n{CYAN}⏺{RESET} {render_markdown(block['text'])}")

                        if block["type"] == "tool_use":
                            tool_name = block["name"]
                            tool_args = block["input"]
                            arg_preview = str(next(iter(tool_args.values()), ""))[:50]
                            print(f"\n{GREEN}⏺ {tool_name.capitalize()}{RESET}({DIM}{arg_preview}{RESET})")

                            result = run_tool(tool_name, tool_args)
                            print(f"  {DIM}⎿  {_result_preview(result)}{RESET}")

                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block["id"],
                                "content": result,
                            })

                    messages.append({"role": "assistant", "content": content_blocks})

                    if not tool_results:
                        break
                    messages.append({"role": "user", "content": tool_results})

            print()

        except (KeyboardInterrupt, EOFError):
            break
        except Exception as err:
            print(f"{RED}⏺ Error: {err}{RESET}")


if __name__ == "__main__":
    main()
