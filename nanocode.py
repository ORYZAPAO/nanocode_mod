#!/usr/bin/env python3
"""nanocode - minimal claude code alternative"""

import glob as globlib, json, os, re, subprocess, urllib.request

# APIキーが設定されている場合はOpenRouter、なければAnthropicを使用
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY")
API_URL = "https://openrouter.ai/api/v1/messages" if OPENROUTER_KEY else "https://api.anthropic.com/v1/messages"
# 環境変数MODELで上書き可能。未設定時はOpenRouter/Anthropicそれぞれのデフォルトモデルを使用
MODEL = os.environ.get("MODEL", "anthropic/claude-opus-4.5" if OPENROUTER_KEY else "claude-opus-4-5")

# ANSIエスケープコード（ターミナル装飾用）
RESET, BOLD, DIM = "\033[0m", "\033[1m", "\033[2m"
BLUE, CYAN, GREEN, YELLOW, RED = (
    "\033[34m",
    "\033[36m",
    "\033[32m",
    "\033[33m",
    "\033[31m",
)


# --- ツール実装 ---


def read(args):
    # ファイルを行番号付きで読み込む。offset/limitで範囲指定可能
    lines = open(args["path"]).readlines()
    offset = args.get("offset", 0)
    limit = args.get("limit", len(lines))
    selected = lines[offset : offset + limit]
    return "".join(f"{offset + idx + 1:4}| {line}" for idx, line in enumerate(selected))


def write(args):
    # ファイルに内容を書き込む（上書き）
    with open(args["path"], "w") as f:
        f.write(args["content"])
    return "ok"


def edit(args):
    # ファイル内の old 文字列を new 文字列に置換する
    text = open(args["path"]).read()
    old, new = args["old"], args["new"]
    if old not in text:
        return "error: old_string not found"
    count = text.count(old)
    # all=true でない場合、old が複数存在するとエラー（誤置換防止）
    if not args.get("all") and count > 1:
        return f"error: old_string appears {count} times, must be unique (use all=true)"
    replacement = (
        text.replace(old, new) if args.get("all") else text.replace(old, new, 1)
    )
    with open(args["path"], "w") as f:
        f.write(replacement)
    return "ok"


def glob(args):
    # パターンに一致するファイルを更新日時降順で列挙する
    pattern = (args.get("path", ".") + "/" + args["pat"]).replace("//", "/")
    files = globlib.glob(pattern, recursive=True)
    files = sorted(
        files,
        key=lambda f: os.path.getmtime(f) if os.path.isfile(f) else 0,
        reverse=True,
    )
    return "\n".join(files) or "none"


def grep(args):
    # 正規表現でファイル群を検索し、マッチした行を最大50件返す
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
    # シェルコマンドをリアルタイムストリーミングで実行し、出力を返す
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
    # ツール名でディスパッチし、エラーは文字列で返す
    try:
        return TOOLS[name][2](args)
    except Exception as err:
        return f"error: {err}"


def make_schema():
    # TOOLS定義からAnthropicのtool_use形式のJSONスキーマを生成する
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
        result.append(
            {
                "name": name,
                "description": description,
                "input_schema": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            }
        )
    return result


def call_api(messages, system_prompt):
    # APIにリクエストを送信し、レスポンスをJSONで返す
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(
            {
                "model": MODEL,
                "max_tokens": 8192,
                "system": system_prompt,
                "messages": messages,
                "tools": make_schema(),
            }
        ).encode(),
        headers={
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
            # OpenRouterはBearerトークン、AnthropicはAPIキーヘッダーを使用
            **({"Authorization": f"Bearer {OPENROUTER_KEY}"} if OPENROUTER_KEY else {"x-api-key": os.environ.get("ANTHROPIC_API_KEY", "")}),
        },
    )
    response = urllib.request.urlopen(request)
    return json.loads(response.read())


def separator():
    # ターミナル幅に合わせた区切り線を返す（最大80文字）
    return f"{DIM}{'─' * min(os.get_terminal_size().columns, 80)}{RESET}"


def render_markdown(text):
    # **太字** をANSIボールドに変換する簡易Markdownレンダラー
    return re.sub(r"\*\*(.+?)\*\*", f"{BOLD}\\1{RESET}", text)


def main():
    print(f"{BOLD}nanocode{RESET} | {DIM}{MODEL} ({'OpenRouter' if OPENROUTER_KEY else 'Anthropic'}) | {os.getcwd()}{RESET}\n")
    messages = []
    system_prompt = f"Concise coding assistant. cwd: {os.getcwd()}"

    while True:
        try:
            print(separator())
            user_input = input(f"{BOLD}{BLUE}❯{RESET} ").strip()
            print(separator())
            if not user_input:
                continue
            # /q または exit で終了
            if user_input in ("/q", "exit"):
                break
            # /c で会話履歴をリセット
            if user_input == "/c":
                messages = []
                print(f"{GREEN}⏺ Cleared conversation{RESET}")
                continue

            messages.append({"role": "user", "content": user_input})

            # エージェントループ: ツール呼び出しがなくなるまでAPIを繰り返し呼ぶ
            while True:
                response = call_api(messages, system_prompt)
                content_blocks = response.get("content", [])
                tool_results = []

                for block in content_blocks:
                    if block["type"] == "text":
                        print(f"\n{CYAN}⏺{RESET} {render_markdown(block['text'])}")

                    if block["type"] == "tool_use":
                        tool_name = block["name"]
                        tool_args = block["input"]
                        # 最初の引数の先頭50文字をプレビュー表示
                        arg_preview = str(list(tool_args.values())[0])[:50]
                        print(
                            f"\n{GREEN}⏺ {tool_name.capitalize()}{RESET}({DIM}{arg_preview}{RESET})"
                        )

                        result = run_tool(tool_name, tool_args)
                        # 結果の先頭60文字をプレビュー表示（複数行の場合は行数も表示）
                        result_lines = result.split("\n")
                        preview = result_lines[0][:60]
                        if len(result_lines) > 1:
                            preview += f" ... +{len(result_lines) - 1} lines"
                        elif len(result_lines[0]) > 60:
                            preview += "..."
                        print(f"  {DIM}⎿  {preview}{RESET}")

                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block["id"],
                                "content": result,
                            }
                        )

                messages.append({"role": "assistant", "content": content_blocks})

                # ツール呼び出しがなければループ終了
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
