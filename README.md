# DeepSeek Local Agent

A local, permission-first coding agent for your desktop, powered exclusively by the **DeepSeek** API.

It behaves like a coding companion (similar to Claude Code / Cursor Agent), but **every file read, file write, and command execution must be explicitly approved by you** through a modal dialog.

---

## Table of contents

1. [Overview](#overview)
2. [Features](#features)
3. [Architecture](#architecture)
4. [Requirements](#requirements)
5. [Installation](#installation)
6. [Configuration](#configuration)
7. [DeepSeek API setup](#deepseek-api-setup)
8. [Running](#running)
9. [Using workspaces](#using-workspaces)
10. [Agent mode vs Ask mode](#agent-mode-vs-ask-mode)
11. [Permissions](#permissions)
12. [Security](#security)
13. [Tools](#tools)
14. [Project structure](#project-structure)
15. [Testing](#testing)
16. [Troubleshooting](#troubleshooting)
17. [Privacy](#privacy)
18. [Limitations](#limitations)
19. [Future improvements](#future-improvements)

---

## Overview

DeepSeek Local Agent is a Python + PySide6 desktop app that talks to the DeepSeek chat API, has access to a curated set of **tools** (file I/O, search, terminal, git), and drives a **tool-calling loop** to complete real coding tasks:

```
User → DeepSeek → Plan → Tool Call → Permission → Execute → Observe → Repeat → Final answer
```

Nothing happens without your consent. The agent literally cannot read a single byte outside the workspace unless you allow it.

---

## Features

- **DeepSeek-only provider** (swap-ready architecture for future providers)
- **Real agent loop** — multi-step tool use, not a simple chatbot
- **Tool calling** via OpenAI-compatible function calling (native DeepSeek support)
- **Streaming responses** — tokens appear live
- **Workspace sandboxing** — all operations confined to a chosen folder
- **Permission system** with `Allow Once` / `Deny` / `Always Allow`
- **Persistent permission rules** in SQLite, scoped to file / directory / workspace / global
- **Audit log** of every tool decision
- **Dangerous command detection** (`rm -rf`, `format`, `DROP DATABASE`, …)
- **Secret detection** before sending file content to the model
- **Sensitive file protection** (`.env`, `*.pem`, `id_rsa`, …)
- **Path traversal + symlink escape prevention**
- **File editing with backups** (`.bak` snapshots before overwrite)
- **16+ tools**: file I/O, search, terminal, git (status/diff/log/branch)
- **Markdown rendering** with code blocks
- **Conversation history** persisted to JSON
- **Context window management** with automatic summarization
- **Dark / light themes**
- **Responsive GUI** — background threads keep the UI fluid during API calls and command execution
- **Keyboard shortcuts** (Ctrl+Enter send, Ctrl+N new chat, Ctrl+O open workspace, Esc stop)

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    PySide6 GUI Layer                      │
│      (Chat, Explorer, Activity, Permission Dialogs)      │
└──────────────────────┬───────────────────────────────────┘
                       │ Qt signals / marshalled events
┌──────────────────────▼───────────────────────────────────┐
│                    Agent Engine                           │
│     (think → tool → observe → repeat, cancellable)       │
└──────┬─────────────────────────────┬─────────────────────┘
       │                             │
       ▼                             ▼
┌──────────────┐              ┌──────────────┐
│ LLM Provider │              │ Tool Registry│
│  (DeepSeek)  │              │  (16 tools)  │
└──────────────┘              └──────┬───────┘
                                     │
                     ┌───────────────┼───────────────┐
                     ▼               ▼               ▼
             ┌──────────────┐ ┌──────────────┐ ┌──────────┐
             │  Permission  │ │  Workspace   │ │ Security │
             │   Manager    │ │   Manager    │ │  Guard   │
             └──────┬───────┘ └──────────────┘ └──────────┘
                    │
                    ▼
             ┌──────────────┐
             │  SQLite DB   │
             │ (rules+audit)│
             └──────────────┘
```

**Key invariant:** the DeepSeek model *never* touches your disk or shell directly. It emits structured tool calls; the runtime validates them, asks you, executes, and returns results.

---

## Requirements

- Python **3.12+**
- A DeepSeek API key ([platform.deepseek.com](https://platform.deepseek.com))
- Internet connection (for the DeepSeek API only)
- OS: Windows 10/11, Linux (X11/Wayland), macOS 12+

---

## Installation

```bash
git clone <your-repo-url> deepseek_agent
cd deepseek_agent

python -m venv .venv

# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
```

---

## Configuration

Copy the example environment file:

```bash
cp .env.example .env
```

Edit `.env`:

```env
DEEPSEEK_API_KEY=sk-your-key-here
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

You can also enter the API key from inside the app (`Settings → API`). It is stored in `data/credentials.json` with `0600` permissions (best-effort on Windows).

**Never commit `.env`** — it is in `.gitignore`.

---

## DeepSeek API setup

1. Create an account at <https://platform.deepseek.com>.
2. Generate an API key.
3. Paste it into `.env` **or** the in-app Settings dialog.
4. Click **Test Connection** in Settings → API to verify.

Supported models (as of writing): `deepseek-chat`, `deepseek-reasoner`. The model ID is fully configurable.

---

## Running

```bash
python main.py
```

The desktop window opens. On first run, you'll be prompted to:
1. Enter your DeepSeek API key
2. Choose a workspace folder
3. Start chatting

---

## Using workspaces

A **workspace** is the folder the agent is allowed to touch. All file operations and commands are confined to it (unless you explicitly allow otherwise via a permission dialog).

- `File → Open Workspace…` or `Ctrl+O`
- Recent workspaces are remembered in `data/settings.json`

The active workspace appears in the top bar and status bar.

---

## Agent mode vs Ask mode

- **Agent mode** — the model can use tools (read, write, run commands). Every tool call requires permission unless you've set an `Always Allow` rule.
- **Ask mode** — the model only answers with text; no tools are exposed. Use it for Q&A about your code without any risk of modification.

Switch with the **Mode** dropdown in the top bar.

---

## Permissions

Every potentially impactful action goes through the permission system:

| Decision          | Behavior                                          |
|-------------------|---------------------------------------------------|
| **Allow Once**    | Approves this specific call only                  |
| **Deny**          | Blocks the call; the model is told it was denied  |
| **Always Allow**  | Persists a rule in SQLite for the same scope      |

Scopes:

- **File** — exact path match
- **Directory** — path prefix match
- **Workspace** — anything inside the current workspace (default for `Always Allow`)
- **Global** — everything (use with care)

**Dangerous** actions (file deletion, dangerous shell commands) *always* require an explicit confirmation, even if an `Always Allow` rule exists.

You can view and reset all rules in `Settings → Permissions`.

---

## Security

Layered defenses:

1. **Workspace sandboxing** — `SecurityGuard.check_path` resolves symlinks and rejects any path outside the workspace root.
2. **Sensitive file policy** — `.env`, `*.pem`, `*.key`, `id_rsa`, `credentials.json`, … require explicit confirmation and are flagged in the dialog.
3. **Secret detection** — before sending file content to the model, common secret patterns (API keys, private keys, `password = …`) are detected and surfaced to the user.
4. **Dangerous command detection** — `rm -rf`, `format`, `shutdown`, `diskpart`, `DROP TABLE`, fork bombs, etc. require explicit consent regardless of stored rules.
5. **No `eval`/`exec`** — tool arguments are parsed with `json.loads` only.
6. **Shell execution** — validated commands are run via `subprocess.run(shell=True, …)` inside the workspace, with a hard timeout.
7. **Log redaction** — the logging filter strips API keys, tokens, and passwords before writing to disk.
8. **Audit log** — every permission decision is appended to `data/agent.db` (`audit_log` table).

---

## Tools

| Tool              | Purpose                                            |
|-------------------|----------------------------------------------------|
| `list_directory`  | List files/folders (up to 3 levels deep)           |
| `read_file`       | Read a text file, optional line range              |
| `write_file`      | Overwrite a file (creates `.bak` backup)           |
| `create_file`     | Create a new file                                  |
| `delete_file`     | Delete a file (dangerous — needs confirmation)     |
| `move_file`       | Move / rename a file                               |
| `copy_file`       | Copy a file                                        |
| `replace_text`    | Exact-substring replacement (surgical edits)       |
| `get_file_info`   | Size, mtime, type                                  |
| `search_files`    | Glob search by filename                            |
| `search_text`     | Grep (plain or regex) across the workspace         |
| `run_command`     | Execute a shell command inside the workspace       |
| `git_status`      | `git status --short --branch`                      |
| `git_diff`        | `git diff` (optionally staged, per-file)           |
| `git_log`         | Recent commits                                     |
| `git_branch`      | Local branches                                     |

Tools are registered in `app/tools/registry.py`. Adding a new tool is a two-file change.

---

## Project structure

```
deepseek_agent/
├── main.py
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
├── app/
│   ├── config.py
│   ├── logging_setup.py
│   ├── providers/       # LLM provider abstraction
│   ├── permissions/     # permission manager + SQLite storage
│   ├── tools/           # 16 built-in tools
│   ├── workspace/       # workspace root + file tree helpers
│   ├── security/        # path/command/secret guards
│   ├── context/         # context window manager
│   ├── conversations/   # JSON conversation store
│   ├── agent/           # agent loop + system prompt
│   └── ui/              # PySide6 GUI
├── data/                # SQLite DB, conversations, settings
├── logs/                # agent.log, errors.log
└── tests/               # pytest suite
```

---

## Testing

```bash
pytest -q
```

The test suite covers permissions, workspace sandboxing, tools, context trimming, and security guards. It uses `MockDeepSeekProvider` and never hits the network.

To run a specific file:

```bash
pytest tests/test_permissions.py -v
```

---

## Troubleshooting

| Symptom                                       | Fix                                                                       |
|-----------------------------------------------|---------------------------------------------------------------------------|
| **"API key is empty"**                        | Settings → API → paste key → Test Connection → Save                       |
| **401 Authentication failed**                 | Key is wrong or revoked. Regenerate at platform.deepseek.com              |
| **429 Rate limit**                            | Wait a bit; DeepSeek enforces per-minute quotas                           |
| **"Path outside workspace"**                  | The agent tried to escape the sandbox — expected and safe                 |
| **GUI freezes**                               | Should never happen — commands and API calls run on worker threads. File an issue. |
| **Long-running command stuck**                | `Esc` to cancel; commands have a 60s default timeout                      |
| **Empty response**                            | Check the model ID in Settings → AI; some IDs are not always available    |

Logs live in `logs/agent.log` and `logs/errors.log`. Secrets are automatically redacted.

---

## Privacy

**What stays local:**
- Your workspace files (only read locally)
- Conversation history (`data/conversations/`)
- Permission rules and audit log (`data/agent.db`)
- API key (`data/credentials.json` or `.env`)
- Logs (`logs/`)

**What is sent to DeepSeek:**
- Your chat messages
- The content of any file the agent explicitly reads via `read_file`
- The output of any command the agent explicitly runs via `run_command`
- Tool definitions (schemas only, no user data)

**Nothing else** leaves your machine. There is no third-party backend.

> ⚠️ **Warning:** Any file you allow the agent to read will be sent to the DeepSeek API for analysis. If a file contains secrets, passwords, or private data, redact it or deny the read.

---

## Limitations

- **DeepSeek-only** — other providers are stubbed but not implemented (by design; the architecture supports them).
- **No image input** — text/tool-calling only. The provider interface can be extended.
- **No inline diff viewer** — file edits show up as tool results; use `git_diff` to review.
- **No auto-commit** — `git` tools are read-only; write operations must be done manually.
- **Single workspace at a time** — switching workspaces starts fresh permissions for the new root.
- **Streaming tool calls** are accumulated client-side; very large tool arguments may take a moment to fully arrive.

---

## Future improvements

- Additional providers (OpenAI, Anthropic, local via Ollama)
- Inline diff viewer with per-hunk apply/reject
- Image input support (when DeepSeek exposes a vision model)
- Multi-workspace tabs
- Plugin system for custom tools
- Voice input
- Code-aware syntax highlighting (tree-sitter)
- Auto-format / lint hooks after edits

---

## License

MIT — use it, fork it, ship it.