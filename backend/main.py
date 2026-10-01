"""LocalRepo AI backend: scans a local repo, retrieves relevant code, asks local Ollama."""
import os
import posixpath
import re
import subprocess
import sys
from collections import Counter

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from retrieval import is_overview, overview_context, retrieve

OLLAMA = "http://localhost:11434"
MODEL = "gemma3:1b"

EXT_LANG = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript", ".ts": "TypeScript",
    ".tsx": "TypeScript", ".java": "Java", ".kt": "Kotlin", ".cpp": "C++", ".c": "C",
    ".h": "C", ".hpp": "C++", ".go": "Go", ".rs": "Rust", ".php": "PHP",
    ".swift": "Swift", ".dart": "Dart", ".html": "HTML", ".css": "CSS",
    ".md": "Markdown", ".json": "JSON", ".yaml": "YAML", ".yml": "YAML",
    ".xml": "XML", ".sql": "SQL",
}
IGNORE_DIRS = {".git", "node_modules", "build", "dist", ".gradle", ".idea", "venv",
               ".venv", "__pycache__"}
MAX_FILE_BYTES = 300_000

SYSTEM_PROMPT = """You are LocalRepo AI, a local software engineering assistant.

You answer questions using evidence from the repository context.

For architecture and overview questions, synthesize the repository
structure, entry points, READMEs, dependencies, and important modules
provided in the context.

Do not invent components that are not supported by the context.

If evidence is incomplete, clearly say what is known and what cannot
be determined.

Always mention the relevant files used as evidence.

Prefer concrete file paths and actual code over generic explanations."""

NO_EVIDENCE = "I couldn't find enough evidence in the indexed repository."

EXPLAIN_PROMPT = """Explain this source file to a developer.

Cover:
- purpose
- important functions/classes
- inputs
- outputs
- dependencies
- overall flow

Only use the provided source code."""

app = FastAPI(title="LocalRepo AI")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# In-memory index (single local user, no DB)
STATE: dict = {"root": None, "name": None, "files": {}}  # rel path -> list[str] lines


def read_text(path: str):
    try:
        if os.path.getsize(path) > MAX_FILE_BYTES:
            return None
        with open(path, "rb") as f:
            raw = f.read()
        if b"\x00" in raw[:4096]:
            return None  # binary
        return raw.decode("utf-8", errors="replace")
    except OSError:
        return None


class RepoReq(BaseModel):
    path: str


class AskReq(BaseModel):
    question: str


class ExplainReq(BaseModel):
    file: str


def ollama_chat(system: str, user: str) -> str:
    try:
        r = requests.post(
            f"{OLLAMA}/api/chat",
            json={"model": MODEL, "stream": False,
                  "options": {"temperature": 0.2, "num_ctx": 8192},
                  "messages": [{"role": "system", "content": system},
                               {"role": "user", "content": user}]},
            timeout=300,
        )
        r.raise_for_status()
        return r.json()["message"]["content"]
    except requests.RequestException as e:
        raise HTTPException(503, f"Ollama unavailable: {e}. Start it with `ollama serve`.")


@app.get("/api/status")
def status():
    try:
        r = requests.get(f"{OLLAMA}/api/tags", timeout=2)
        names = [m["name"] for m in r.json().get("models", [])]
        return {"connected": True, "model": MODEL, "model_available": MODEL in names}
    except Exception:
        return {"connected": False, "model": MODEL, "model_available": False}


PICKER = (
    "import tkinter as tk\nfrom tkinter import filedialog\n"
    "r = tk.Tk(); r.withdraw(); r.attributes('-topmost', True)\n"
    "p = filedialog.askdirectory(title='Select repository folder', mustexist=True)\n"
    "print(p or '', end='')"
)


@app.get("/api/browse")
def browse():
    """Open a native folder picker on the machine running the backend (local app)."""
    try:
        out = subprocess.run([sys.executable, "-c", PICKER], capture_output=True, text=True, timeout=300)
    except (subprocess.TimeoutExpired, OSError) as e:
        raise HTTPException(500, f"Folder picker failed: {e}")
    if out.returncode != 0:
        raise HTTPException(500, "Folder picker unavailable (tkinter missing?)")
    path = out.stdout.strip()
    return {"path": os.path.normpath(path) if path else None}


@app.post("/api/repo")
def load_repo(req: RepoReq):
    root = os.path.abspath(os.path.expanduser(req.path.strip().strip('"')))
    if not os.path.isdir(root):
        raise HTTPException(400, f"Not a directory: {root}")
    files: dict = {}
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in IGNORE_DIRS]
        for fn in fns:
            if fn.startswith(".env"):
                continue
            ext = os.path.splitext(fn)[1].lower()
            if ext not in EXT_LANG:
                continue
            full = os.path.join(dp, fn)
            text = read_text(full)
            if text is None:
                continue
            rel = os.path.relpath(full, root).replace("\\", "/")
            files[rel] = text.splitlines()
    langs = Counter(EXT_LANG[os.path.splitext(p)[1].lower()] for p in files)
    STATE.update(root=root, name=os.path.basename(root) or root, files=files,
                 langs=[l for l, _ in langs.most_common()])
    return {"name": STATE["name"], "file_count": len(files),
            "languages": [l for l, _ in langs.most_common()],
            "files": sorted(files)}


@app.get("/api/file")
def get_file(path: str):
    rel, lines = lookup_file(path)
    return {"path": rel, "content": "\n".join(lines), "line_count": len(lines)}


def resolve_path(path: str):
    """Map a user/AI-supplied path to an indexed relative path (or None).

    Accepts backslashes, ./ and ../, absolute paths under the repo root, a leading repo-name
    folder, different case, and an unambiguous trailing suffix.
    """
    files = STATE["files"]
    if not files:
        return None
    p = path.strip().strip('"').replace("\\", "/")
    root = (STATE["root"] or "").replace("\\", "/").rstrip("/")
    if root and p.lower().startswith(root.lower() + "/"):
        p = p[len(root) + 1:]
    p = posixpath.normpath(p).lstrip("/")
    if p in files:
        return p
    low = {f.lower(): f for f in files}
    segs = p.split("/")
    if segs and segs[0].lower() == (STATE["name"] or "").lower():  # repo-name prefix
        segs = segs[1:]
    for i in range(len(segs)):  # progressively drop leading segments
        cand = "/".join(segs[i:])
        if cand in files:
            return cand
        if cand.lower() in low:
            return low[cand.lower()]
    tail = "/".join(segs).lower()
    hits = [f for f in files if f.lower().endswith("/" + tail)]
    return hits[0] if len(hits) == 1 else None


def lookup_file(path: str):
    if not STATE["root"]:
        raise HTTPException(404, "No repository loaded. Click Load again (the backend may have restarted).")
    rel = resolve_path(path)
    if rel is None:
        raise HTTPException(404, f"File not in index: {path}")
    return rel, STATE["files"][rel]


@app.post("/api/ask")
def ask(req: AskReq):
    if not STATE["root"]:
        raise HTTPException(400, "Load a repository first.")
    files = STATE["files"]
    if is_overview(req.question):
        context, sources = overview_context(STATE["name"], files, STATE["langs"])
        mode = "overview"
    else:
        results = retrieve(req.question, files)
        mode = "search"
        if not results:  # nothing relevant: don't let a 1B model guess
            return {"answer": NO_EVIDENCE, "sources": [], "mode": mode}
        context = f"Repository: {STATE['name']}\n\n" + "\n".join(
            f"--- {r['file']} (lines {r['start_line']}-{r['end_line']}) ---\n{r['code']}" for r in results)
        sources = []
        for r in results:
            if r["file"] not in [x["file"] for x in sources]:
                sources.append({"file": r["file"], "path": r["file"], "start_line": r["start_line"],
                                "end_line": r["end_line"], "relevance": r["score"]})
    user = "REPOSITORY CONTEXT:\n" + context + f"\n\nQUESTION: {req.question}"
    if mode == "overview":
        user += ("\n\nAnswer as a short bullet list of the major components. Use ONLY directory and file "
                 "names that appear in the context above. Do not attach a file name to each bullet; "
                 "the supporting files are listed separately. Do not mention anything that is not in the context.")
    return {"answer": ollama_chat(SYSTEM_PROMPT, user), "sources": sources, "mode": mode}


@app.post("/api/explain")
def explain(req: ExplainReq):
    rel, lines = lookup_file(req.file)
    code = "\n".join(lines)[:12000]
    answer = ollama_chat("You are LocalRepo AI, a local software engineering assistant.",
                         f"{EXPLAIN_PROMPT}\n\nFile: {rel}\n\n```\n{code}\n```")
    return {"file": req.file, "explanation": answer}
