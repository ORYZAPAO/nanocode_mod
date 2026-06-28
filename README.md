# nanocode

Minimal Claude Code alternative. Single Python file, zero dependencies, ~250 lines.

Built using Claude Code, then used to build itself.

![screenshot](screenshot.png)

## Features

- Full agentic loop with tool use
- Tools: `read`, `write`, `edit`, `glob`, `grep`, `bash`
- Conversation history
- Colored terminal output

## Usage

### Anthropic

```bash
export ANTHROPIC_API_KEY="your-key"
python nanocode.py
```

### OpenAI

```bash
export OPENAI_API_KEY="your-key"
python nanocode.py
```

### OpenRouter

Use [OpenRouter](https://openrouter.ai) to access any model via the OpenAI-compatible protocol:

```bash
export OPENROUTER_API_KEY="your-key"
python nanocode.py
```

To use a different model:

```bash
export OPENROUTER_API_KEY="your-key"
export MODEL="openai/gpt-5.2"
python nanocode.py
```

## API Protocol

| Environment Variable | Provider | Protocol |
|----------------------|----------|----------|
| `ANTHROPIC_API_KEY` | Anthropic | Anthropic native (`/v1/messages`) |
| `OPENAI_API_KEY` | OpenAI | OpenAI-compatible (`/v1/chat/completions`) |
| `OPENROUTER_API_KEY` | OpenRouter | OpenAI-compatible (`/v1/chat/completions`) |

Priority order when multiple keys are set: `OPENROUTER_API_KEY` > `OPENAI_API_KEY` > `ANTHROPIC_API_KEY`

## Commands

- `/c` - Clear conversation
- `/q` or `exit` - Quit

## Tools

| Tool | Description |
|------|-------------|
| `read` | Read file with line numbers, offset/limit |
| `write` | Write content to file |
| `edit` | Replace string in file (must be unique) |
| `glob` | Find files by pattern, sorted by mtime |
| `grep` | Search files for regex |
| `bash` | Run shell command |

## Example

```
────────────────────────────────────────
❯ what files are here?
────────────────────────────────────────

⏺ Glob(**/*.py)
  ⎿  nanocode.py

⏺ There's one Python file: nanocode.py
```

## License

MIT
