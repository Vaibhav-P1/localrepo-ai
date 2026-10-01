# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

LocalRepo AI: a privacy-first assistant that answers questions about a local repo using a local Ollama model (`gemma3:1b` at `http://localhost:11434`). Source code must never go to a cloud API. No database, auth, embeddings, or vector store by design.

## Commands

Backend (Python/FastAPI, run from `backend/`):
```
pip install -r requirements.txt
python -m uvicorn main:app --port 8000          # add --reload for dev
python test_retrieval.py <repo_path> [--llm]    # smoke test; needs the server running
```
Frontend (run from `frontend/`):
```
npm install
npm run dev      # http://localhost:5173, proxies /api -> localhost:8000
npm run build    # tsc -b && vite build (use as the type-check)
npm run lint     # oxlint
```
There is no unit-test framework; `test_retrieval.py` hits the live API with five fixed questions (architecture, startup, specific component, port lookup, nonexistent feature) and prints retrieved sources (`--llm` also prints answers). Needs Ollama running with `gemma3:1b` pulled.

## Architecture

**Request flow:** `POST /api/repo` scans a directory into an in-memory `STATE` dict (`files`: rel-path -> list of lines, plus name/langs) in `backend/main.py`. `POST /api/ask` then routes by intent, builds a context string, and calls Ollama `/api/chat` (non-streaming) through `ollama_chat`. The index is a single global, so there is one repo at a time and it is lost on restart.

**Two retrieval paths** (`backend/retrieval.py`, no dependencies):
- `is_overview(q)` matches broad questions (architecture, overview, "explain this project") and uses `overview_context()`: a curated bundle of READMEs, entry-point files, server/API files, dependency files and directory stats, capped around 9000 chars. The user message also gets an instruction to answer as a bullet list using only names in the context.
- Otherwise `retrieve()` chunks every file into 40-line pieces, scores them (filename match, symbol match, phrase match, path relevance, IDF-weighted keywords, plus boosts for entry points on "start" questions, port numbers on "port" questions, and auth/api/db topic words), and takes the top chunks within `MAX_CONTEXT_CHARS`. Chunks below `MIN_SCORE` are dropped.
- If no chunk survives, `/api/ask` returns the fixed no-evidence string **without calling the model**. This guards against 1B-model hallucination, so keep it.
- Tokens are crudely stemmed (suffix strip, then 6-char prefix) on both questions and code, so `monitoring` matches `monitor`. Changes to `stem`/`STOP` affect all ranking.

`/api/ask` returns `{answer, sources[{file,start_line,end_line}], mode}`. Sources come from the retrieved chunks (or the files in the overview), not from parsing the model's answer.

**Folder picker:** `GET /api/browse` spawns `python -c` with `tkinter` in a subprocess to show a native folder dialog on the backend machine and returns the path (or `null` on cancel). This works only because the backend runs locally on the user's desktop. It is not suitable for remote deployment.

**Frontend** (`frontend/src`): `App.tsx` holds all state (status polling every 5s, repo, chat messages, file viewer, theme). `Answer.tsx` renders the model's Markdown with react-markdown, turning any path or backticked name that resolves to an indexed file into a clickable chip (matching unique suffixes, e.g. `run_all.py` -> `a/b/run_all.py`) that opens the viewer with the source's line range highlighted. The LLM outputs plain Markdown only, never HTML. Styling is one file, `index.css`, using CSS variables with `data-theme` light/dark.

## Constraints and gotchas

- The scanner ignores `.git`, `node_modules`, `build`, `dist`, `.gradle`, `.idea`, `venv`/`.venv`, `__pycache__`, `.env*`, binaries and files over 300 KB, and only reads the extensions in `EXT_LANG`. Never modify or execute files in the scanned repo.
- Context is deliberately small for a 1B model. Don't raise limits or add prompt text without re-running `test_retrieval.py`.
- When editing Python files with generated snippets, beware of escape sequences like `\n` being mangled; check the result with `python -c "import main"`.
- Visual direction is cream background, 3px black borders and offset dark-red shadows, with no gradients and no rounded corners. Match it for new UI.
- A reference repo for testing retrieval (VIGYAAN) was kept at `D:\VIGYAAN-main`, outside this repo.
