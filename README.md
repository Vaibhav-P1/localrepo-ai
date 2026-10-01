# LocalRepo AI

> **Understand your codebase. Keep your code local.**

LocalRepo AI is a privacy-first developer assistant. Point it at a local repository, ask questions in plain English, and get answers grounded in your actual code. The AI runs entirely on your machine through [Ollama](https://ollama.com), so **your source code is never sent to a cloud API**.

---

## Table of Contents
- [Why LocalRepo AI](#why-localrepo-ai)
- [Features](#features)
- [How It Works](#how-it-works)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Usage](#usage)
- [API Reference](#api-reference)
- [Privacy and Safety](#privacy-and-safety)
- [Limitations](#limitations)
- [Roadmap](#roadmap)

---

## Why LocalRepo AI

Cloud coding assistants need you to upload proprietary code to third-party servers. LocalRepo AI removes that trade-off: scanning, search and inference all happen on your own machine.

## Features

- **100% local inference** with Ollama and `gemma3:1b`
- **Repository scanner** with language detection (ignores `.git`, `node_modules`, `build`, `dist`, `.gradle`, `.idea`, `venv`, `__pycache__`, `.env*` files and binaries)
- **Overview-aware retrieval**: broad questions such as "Explain the architecture" get a curated repository overview (READMEs, entry points, API files, dependency files)
- **Ranked code search** for specific questions, with no embeddings or vector database
- **Source references** with file paths and line ranges on every answer
- **File explorer and code viewer** with line numbers; clicking a source highlights the matched lines
- **Explain File**: one-click local-AI explanation of any file
- **Ollama status indicator** (`● Ollama Connected` / `○ Ollama Offline`) with start instructions
- **No-guess fallback**: if nothing relevant is found, it answers *"I couldn't find enough evidence in the indexed repository."* without calling the model
- **Light and dark themes**

## How It Works

```
Question ──► Intent detection
               ├─ Broad / architecture ──► Repository overview context
               │                           (READMEs, entry points, API files, deps, dirs)
               └─ Specific ──────────────► Ranked chunk search
                                           (filename, symbol, phrase, path, IDF keywords)
                         │
                         ▼
              Compact context (size-limited for a 1B model)
                         │
                         ▼
              Ollama (gemma3:1b, localhost:11434)
                         │
                         ▼
              Answer + source files with line ranges
```

**Retrieval ranking order (specific questions):**
1. Exact filename match
2. Exact function/class/symbol match
3. Multi-word phrase match
4. Filename and path relevance
5. IDF-weighted keyword frequency (rare terms count more, so words like "project" or "system" do not dominate)
6. README relevance

Extra boosts apply for entry points on startup questions, port numbers on "port" questions, and topic words for authentication, API and database questions. Generic file types (HTML, CSS, JSON) are down-weighted unless their filename matches.

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React, Vite, TypeScript, plain CSS |
| Backend | Python, FastAPI, Uvicorn, Requests |
| AI | Ollama (local inference), Gemma 3 1B (`gemma3:1b`) |
| Retrieval | Custom keyword, symbol and filename ranking with simple stemming and IDF weighting |

## Project Structure

```
LocalRepo-AI/
├── backend/
│   ├── main.py             # FastAPI app: scanner, endpoints, Ollama client, prompts
│   ├── retrieval.py        # Intent detection, overview builder, ranked search
│   ├── test_retrieval.py   # Retrieval smoke test against a real repo
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── App.tsx         # UI: sidebar, chat, sources, code viewer
│       └── index.css       # Editorial / brutalist theme (light + dark)
└── README.md
```

## Getting Started

### Prerequisites
- [Ollama](https://ollama.com) installed and running
- Python 3.10+
- Node.js 18+

### 1. Pull the model
```bash
ollama pull gemma3:1b
ollama serve        # skip if Ollama is already running
```

### 2. Start the backend
```bash
cd backend
pip install -r requirements.txt
python -m uvicorn main:app --port 8000
```

### 3. Start the frontend
```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**. The dev server proxies `/api` to the backend on port 8000.

## Usage

1. Paste a local repository path (for example `D:\projects\my-app`) and click **Load**.
2. Check the sidebar: repository name, file count, detected languages and the *Local only* badge.
3. Ask a question, for example:
   - "Explain the architecture of this project."
   - "How does the application start?"
   - "Where is the authentication logic implemented?"
4. Read the answer and the **Relevant Sources** list beneath it.
5. Click a source (or any file in the sidebar) to open it, then click **Explain File**.

### Retrieval smoke test
```bash
cd backend
python test_retrieval.py "path/to/your/repo" --llm
```
Runs five sample questions (architecture, startup, a specific component, a port lookup, and a nonexistent feature) and prints the retrieved sources and answers. The backend must be running.

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/status` | Ollama connection and model availability |
| POST | `/api/repo` | Scan a repository: `{ "path": "..." }` returns name, file count, languages, file list |
| GET | `/api/file?path=...` | Contents of an indexed file |
| POST | `/api/ask` | `{ "question": "..." }` returns answer, sources and mode (`overview` or `search`) |
| POST | `/api/explain` | `{ "file": "..." }` returns a file explanation |

## Privacy and Safety

- Source code is read from disk and sent only to Ollama at `http://localhost:11434`.
- No cloud APIs, accounts, telemetry or database. The index lives in memory.
- Repository files are **never modified or executed**.
- `.env*` files, binaries and files over 300 KB are skipped.
- The system prompt tells the model to use only the provided context, not to invent files or behavior, and to say when evidence is missing.

## Limitations

- `gemma3:1b` is a small model. Retrieval and source lists are reliable, but generated answers can contain mistakes, so verify against the linked sources.
- Retrieval is keyword-based. Questions with no vocabulary overlap with the code may return no evidence.
- The index is rebuilt on each Load and is not persisted.
- Context is deliberately small, so very large repositories are summarised rather than read in full.

## Roadmap

- Syntax highlighting in the code viewer
- Streaming answers
- Optional larger local models
- Incremental re-indexing on file changes
