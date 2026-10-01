"""Simple, dependency-free retrieval: intent detection, repo overview, ranked chunk search."""
import math
import os
import re
from collections import Counter

CHUNK_LINES = 40
MAX_CONTEXT_CHARS = 6000
TOP_CHUNKS = 6
MIN_SCORE = 6.0

STOP = set("""the is are a an of to in on for and or how what does do why where which this that with
from it its be as at by me my explain project work works use used about tell show can you give
describe application app main system code repository repo implemented implementation""".split())


def stem(w: str) -> str:
    w = w.lower()
    for suf in ("ing", "ed", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            w = w[: -len(suf)]
            break
    return w[:6]


def tokenize(text: str):
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    return [stem(t) for t in re.findall(r"[A-Za-z][A-Za-z0-9]+", text)]


STOP_STEMS = {stem(s) for s in STOP}


def question_terms(q: str):
    terms = [t for t in tokenize(q) if t not in STOP_STEMS]
    return terms or tokenize(q)


# ---------- intent ----------
OVERVIEW_PATTERNS = [
    r"architecture", r"overview", r"explain (this|the) (project|repo|repository|codebase|app|application)",
    r"how (does|do) (this|the) (project|repo|repository|codebase|app|application|system) work",
    r"main (components|modules|parts)", r"(project|repo|codebase) (is )?structur",
    r"how is (this|the) (project|repo|repository|codebase) (structured|organi[sz]ed)",
    r"what (does|is) (this|the) (project|repo|repository|codebase|app|application)",
    r"high.?level", r"tech(nology)?\s*stack", r"technologies (used|does)", r"(frameworks|libraries) (used|does)", r"built with", r"describe (this|the) (project|repo|codebase)",
]


def is_overview(q: str) -> bool:
    ql = q.lower()
    return any(re.search(p, ql) for p in OVERVIEW_PATTERNS)


START_RE = re.compile(r"\b(start|starts|launch|launches|boot|entry|begin|run|runs|startup)\b", re.I)

TOPIC_BOOSTS = {
    "auth": ("auth", "login", "signup", "user", "firebase", "token", "session"),
    "api": ("api", "route", "server", "endpoint", "controller", "router"),
    "db": ("database", "db", "repository", "dao", "model", "schema", "sqlite", "mongodb", "postgres"),
    "architecture": ("readme", "server", "main", "run", "api"),
}
TOPIC_TRIGGERS = {
    "auth": r"auth|login|sign.?up|password|token|session|firebase",
    "api": r"\bapi\b|route|endpoint|controller|router|server",
    "db": r"database|\bdb\b|sqlite|mongo|postgres|schema|\bdao\b|\bmodels?\b",
}

ENTRY_NAMES = {"main.py", "app.py", "server.py", "run.py", "run_all.py", "manage.py", "index.js",
               "index.ts", "app.tsx", "app.jsx", "main.tsx", "main.jsx", "main.js", "main.ts",
               "mainactivity.kt", "application.kt", "main.go", "main.rs", "main.dart", "main.java",
               "__main__.py"}
DEP_NAMES = {"requirements.txt", "package.json", "build.gradle", "settings.gradle", "pubspec.yaml",
             "pom.xml", "build.gradle.kts", "pyproject.toml"}


def _base(p: str) -> str:
    return os.path.basename(p).lower()


def _depth(p: str) -> int:
    return p.count("/")


# ---------- overview ----------
def overview_context(name: str, files: dict, langs: list):
    paths = sorted(files)
    top_dirs = sorted({p.split("/")[0] for p in paths if "/" in p})
    readmes = sorted([p for p in paths if _base(p).startswith("readme")], key=lambda p: (_depth(p), p))
    entries = sorted([p for p in paths if _base(p) in ENTRY_NAMES], key=lambda p: (_depth(p), p))
    deps = sorted([p for p in paths if _base(p) in DEP_NAMES], key=lambda p: (_depth(p), p))
    # servers/api files often are the real architecture
    servers = [p for p in paths if re.search(r"(server|api|routes?|orchestrat|pipeline)", _base(p))
               and p not in entries and p.endswith((".py", ".js", ".ts", ".kt", ".go", ".java"))]
    servers.sort(key=lambda p: (_depth(p), p))

    # directory -> file count, to show which are substantial
    dir_counts = Counter("/".join(p.split("/")[:2]) for p in paths if p.count("/") >= 1)
    sub_dirs = [f"{d}/ ({c} files)" for d, c in dir_counts.most_common(25)]

    sources, parts = [], []

    def add_file(p, limit, label):
        text = "\n".join(files[p])[:limit]
        parts.append(f"--- {label}: {p} ---\n{text}")
        lines = len(files[p])
        sources.append({"file": p, "start_line": 1, "end_line": min(lines, text.count("\n") + 1)})

    parts.append(f"PROJECT:\n{name}\n\nLANGUAGES:\n{', '.join(langs)}")
    parts.append("TOP-LEVEL DIRECTORIES:\n" + "\n".join(d + "/" for d in top_dirs[:25]))
    parts.append("SUBDIRECTORIES (by size):\n" + "\n".join(sub_dirs))
    important = (entries[:8] + servers[:12] + deps[:4] + readmes[:6])
    parts.append("IMPORTANT FILES:\n" + "\n".join(important))

    for p in readmes[:3]:
        add_file(p, 1800 if p == readmes[0] else 1000, "README")
    for p in entries[:3]:
        add_file(p, 1200, "ENTRY POINT")
    for p in servers[:2]:
        add_file(p, 700, "SERVICE/API FILE")
    for p in deps[:2]:
        add_file(p, 500, "DEPENDENCIES")
    # trim to keep the prompt small for a 1B model
    return "\n\n".join(parts)[:9000], sources


# ---------- ranked search ----------
DEF_RE = re.compile(
    r"^\s*(?:export\s+)?(?:async\s+)?(?:def|class|function|func|fn|interface|struct|impl|fun)\s+(\w+)")
PORT_RE = re.compile(r"port\W{0,4}\d{3,5}|:\s*\d{4,5}\b|\b\d{4,5}\b", re.I)


def retrieve(question: str, files: dict):
    terms = question_terms(question)
    tset = set(terms)
    ql = question.lower()
    wants_start = bool(START_RE.search(ql))
    wants_port = "port" in ql
    topics = [t for t, rx in TOPIC_TRIGGERS.items() if re.search(rx, ql)]
    boost_words = {stem(w) for t in topics for w in TOPIC_BOOSTS[t]}

    # quoted / adjacent-term phrases, e.g. "driver distraction"
    words = [w for w in re.findall(r"[a-z0-9]+", ql) if stem(w) not in STOP_STEMS]
    phrases = [f"{a} {b}" for a, b in zip(words, words[1:])]

    # build chunks + document frequency for IDF weighting
    chunks = []
    df = Counter()
    for rel, lines in files.items():
        for start in range(0, max(len(lines), 1), CHUNK_LINES):
            chunk = lines[start:start + CHUNK_LINES]
            if not chunk:
                continue
            text = "\n".join(chunk)
            counts = Counter(tokenize(text))
            for t in tset:
                if counts[t]:
                    df[t] += 1
            chunks.append((rel, start, chunk, text, counts))
    n = max(len(chunks), 1)
    idf = {t: math.log(1 + n / (1 + df[t])) for t in tset}  # rare terms weigh more

    scored = []
    for rel, start, chunk, text, counts in chunks:
        base = _base(rel)
        ptoks = set(tokenize(rel))
        stem_name = tokenize(os.path.splitext(base)[0])
        score = 0.0
        # 1. exact filename match
        if base in ql or os.path.splitext(base)[0] in ql.replace(" ", "_") and len(base) > 4:
            score += 30
        # 2. exact symbol match
        for ln in chunk:
            m = DEF_RE.match(ln)
            if m and tset & set(tokenize(m.group(1))):
                sym = set(tokenize(m.group(1)))
                score += 12 if sym <= tset else 6
        # 3. phrase match
        low = text.lower().replace("_", " ")
        pathlow = rel.lower().replace("_", " ").replace("/", " ")
        for ph in phrases:
            if ph in low:
                score += 8
            if ph in pathlow:
                score += 10
        # 4. filename / path relevance
        score += 6 * len(tset & ptoks) * (1 + 0.5 * len(tset & set(stem_name)))
        # 5. keyword frequency (idf-weighted, capped)
        score += sum(min(counts[t], 4) * idf[t] for t in tset)
        # topic and intent boosts
        if boost_words:
            score += 4 * len(boost_words & ptoks)
        if wants_start and base in ENTRY_NAMES:
            score += 30 - 6 * min(_depth(rel), 4)
            if re.search(r"__main__|\.run\(|Popen|subprocess|listen\(", text):
                score += 6
        if wants_port and PORT_RE.search(text) and score > 0:
            score += 8
        # 6. README relevance
        if base.startswith("readme") and score > 0:
            score += 3
        # generic file types shouldn't win on incidental words
        if base.endswith((".html", ".css", ".json", ".xml", ".svg")) and not (tset & set(stem_name)):
            score *= 0.4
        if score >= MIN_SCORE:
            scored.append((score, rel, start, chunk))

    scored.sort(key=lambda x: -x[0])
    results, total, per_file = [], 0, Counter()
    for score, rel, start, chunk in scored:
        if per_file[rel] >= 2:
            continue
        code = "\n".join(chunk)
        if total + len(code) > MAX_CONTEXT_CHARS and results:
            break
        results.append({"file": rel, "start_line": start + 1, "end_line": start + len(chunk),
                        "code": code, "score": round(score, 1)})
        per_file[rel] += 1
        total += len(code)
        if len(results) >= TOP_CHUNKS:
            break
    return results
