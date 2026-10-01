"""LocalRepo AI backend: scans a local repo, retrieves relevant code, asks local Ollama."""
import os
import re
from collections import Counter

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

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
CHUNK_LINES = 40
MAX_CONTEXT_CHARS = 6000
TOP_CHUNKS = 6

SYSTEM_PROMPT = """You are LocalRepo AI, a local software engineering assistant.

Answer questions ONLY using the repository context provided.

Do not invent files, functions, classes, APIs, or behavior.

If the context does not contain enough information, say:
'I couldn't find enough evidence in the indexed repository.'

Always mention relevant source files.

Clearly distinguish facts from inference."""

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


def tokenize(text: str):
    # split camelCase / snake_case / paths into lowercase words
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    # crude stemming: 5-char prefix so "monitoring"/"monitor", "retrieval"/"retrieve" match
    return [t[:5] for t in re.findall(r"[A-Za-z][A-Za-z0-9]{1,}", text.lower())]


STOP = set("the is are a an of to in on for and or how what does do why where which this that "
           "with from it its be as at by me my explain project work works use used about "
           "tell show can you".split())


STOP_STEMS = {t[:5] for t in STOP}


def question_terms(q: str):
    return [t for t in tokenize(q) if t not in STOP_STEMS]


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
    STATE.update(root=root, name=os.path.basename(root) or root, files=files)
    langs = Counter(EXT_LANG[os.path.splitext(p)[1].lower()] for p in files)
    return {"name": STATE["name"], "file_count": len(files),
            "languages": [l for l, _ in langs.most_common()],
            "files": sorted(files)}


@app.get("/api/file")
def get_file(path: str):
    lines = STATE["files"].get(path)
    if lines is None:
        raise HTTPException(404, "File not in index")
    return {"path": path, "content": "\n".join(lines), "line_count": len(lines)}


DEF_RE = re.compile(r"^\s*(?:export\s+)?(?:async\s+)?(?:def|class|function|func|fn|interface|struct|impl)\s+(\w+)")


def retrieve(question: str):
    terms = question_terms(question)
    if not terms:
        terms = tokenize(question)
    term_set = set(terms)
    scored = []
    for rel, lines in STATE["files"].items():
        path_tokens = set(tokenize(rel))
        path_score = 3 * len(term_set & path_tokens)
        n = len(lines)
        for start in range(0, max(n, 1), CHUNK_LINES):
            chunk = lines[start:start + CHUNK_LINES]
            if not chunk:
                continue
            text = "\n".join(chunk)
            counts = Counter(tokenize(text))
            score = sum(min(counts[t], 5) for t in term_set)
            if score == 0 and path_score == 0:
                continue
            # bonus: function/class names matching the question
            for ln in chunk:
                m = DEF_RE.match(ln)
                if m and term_set & set(tokenize(m.group(1))):
                    score += 4
            score += path_score
            if rel.lower().endswith(".md") and start == 0:
                score += 1  # READMEs help architecture questions
            if score > 0:
                scored.append((score, rel, start, chunk))
    scored.sort(key=lambda x: -x[0])
    results, total, per_file = [], 0, Counter()
    for score, rel, start, chunk in scored:
        if per_file[rel] >= 2:
            continue
        code = "\n".join(chunk)
        if total + len(code) > MAX_CONTEXT_CHARS and results:
            break
        results.append({"file": rel, "start_line": start + 1,
                        "end_line": start + len(chunk), "code": code, "score": score})
        per_file[rel] += 1
        total += len(code)
        if len(results) >= TOP_CHUNKS:
            break
    return results


def tree_summary(limit=60):
    return "\n".join(sorted(STATE["files"])[:limit])


@app.post("/api/ask")
def ask(req: AskReq):
    if not STATE["root"]:
        raise HTTPException(400, "Load a repository first.")
    results = retrieve(req.question)
    ctx = [f"Repository: {STATE['name']}", "File list (partial):", tree_summary(), ""]
    for r in results:
        ctx.append(f"--- {r['file']} (lines {r['start_line']}-{r['end_line']}) ---\n{r['code']}")
    if not results:
        ctx.append("(No matching code found.)")
    user = "REPOSITORY CONTEXT:\n" + "\n".join(ctx) + f"\n\nQUESTION: {req.question}"
    answer = ollama_chat(SYSTEM_PROMPT, user)
    sources = []
    for r in results:
        if r["file"] not in [s["file"] for s in sources]:
            sources.append({"file": r["file"], "start_line": r["start_line"],
                            "end_line": r["end_line"]})
    return {"answer": answer, "sources": sources, "chunks_used": len(results)}


@app.post("/api/explain")
def explain(req: ExplainReq):
    lines = STATE["files"].get(req.file)
    if lines is None:
        raise HTTPException(404, "File not in index")
    code = "\n".join(lines)[:12000]
    answer = ollama_chat("You are LocalRepo AI, a local software engineering assistant.",
                         f"{EXPLAIN_PROMPT}\n\nFile: {req.file}\n\n```\n{code}\n```")
    return {"file": req.file, "explanation": answer}
