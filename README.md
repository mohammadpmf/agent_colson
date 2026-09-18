# Local Coding Agent

A Python desktop coding assistant built with **PySide6**. This repository does not contain a Django server. It supports GapGPT and DeepSeek through their chat-completions endpoints.

## Run

Requires Python 3.12+:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python main.py
```

Open **Settings**, select the provider, enter its key, URL and model, and test the connection. Choose a workspace with **File → Open Workspace** before using Agent mode. Ask mode can be used without a workspace.

Credentials are stored in `data/credentials.json`; settings, permission rules and conversations stay under `data/`. These directories are excluded from Git. Credentials are local plaintext, with best-effort file permissions.

## Conversations and text direction

- Messages are saved automatically when sending and when a response finishes, including a stopped partial response.
- Click a title in **Recent Chats**, or select it and press Enter, to reopen it. Continue typing to append to the same conversation.
- Opening a conversation restores its workspace, messages and tool activity. The next request uses the provider/model currently selected in Settings.
- If the saved workspace has disappeared, you can still read the conversation or use Ask mode; select a workspace before using Agent mode.
- A running response must finish or stop before switching conversations or workspaces. This prevents responses from being saved into the wrong chat.
- Persian/Arabic and English paragraphs use Unicode first-strong-character direction detection. Code blocks remain left-to-right. The composer sets direction independently for each paragraph.
- Markdown supports headings, lists, tables, bold, inline code and fenced code. Raw HTML is displayed as text; Markdown images are displayed as their alternate text.
- Saving uses a temporary file followed by replacement so a failed write preserves the previous saved conversation. The UI reports save failures.

Shortcuts: **Ctrl+Enter** send, **Ctrl+N** new chat, **Ctrl+O** workspace, **Ctrl+L** focus input, **Esc** stop.

## Agent and permissions

Agent mode exposes tools for files, searching, shell commands and read-only Git operations. Ask mode does not execute tools. File and command tools use permission requests; existing rules can allow subsequent operations. Dangerous operations and sensitive reads require fresh confirmation. **Allow Once** works without granting a persistent rule.

Workspace file paths are resolved and checked before operations. Searches skip ignored dependency folders, symlinks, sensitive filenames and files matching secret patterns. Secret detection is heuristic, not a guarantee. Read-only Git tools and file metadata inspection do not currently prompt.

**Shell commands are not isolated by an operating-system sandbox.** Their working directory is the workspace, but an approved command can access anything allowed by your OS account. Review commands before approving them.

Network requests and agent execution run in background workers; permission dialogs and UI updates run on the GUI thread. Stop requests are cooperative: an in-flight HTTP request or shell command may finish or time out before cancellation completes. Closing during a run requests cancellation; close again once it stops.

The streaming checkbox is honored. If a backend does not support streaming, disable it in Settings. Failed streaming requests are not silently repeated. The legacy file-edit-mode selector is disabled because permission rules control edits.

## Tests

No API key or network is needed:

```powershell
python -m unittest discover -s tests -v
python -m compileall -q app main.py
```

The regression suite checks bidirectional rendering, reopening/continuing saved conversations, atomic saves, malformed history, complete tool exchanges, error states, permission decisions, search exclusions, secret redaction and GUI thread delivery.

For reproducible offscreen screenshots of both themes:

```powershell
python tests/render_preview.py
```

Images are written to `artifacts/` (ignored by Git). The preview uses a temporary workspace and synthetic messages.

## Structure

- `app/ui/`: PySide6 windows, Markdown chat, project explorer and worker helpers
- `app/agent/`: tool-calling loop and system prompt
- `app/providers/`: GapGPT, DeepSeek and an offline mock
- `app/conversations/`: JSON persistence
- `app/context/`: tool-history repair and context trimming
- `app/tools/`: filesystem, search, shell and Git tools
- `app/permissions/`, `app/security/`: permission storage and path/content checks
- `tests/`: offline regressions and visual preview

Context trimming retains complete tool exchanges and discards older exchanges when over budget. Token counts are estimates; a single oversized latest exchange is retained and may still exceed the provider's limit. Conversation history is local and is sent to the configured provider when you continue chatting. Approved file content and tool output may also be sent.
