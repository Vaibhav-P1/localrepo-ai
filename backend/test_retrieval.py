"""Retrieval smoke test: python test_retrieval.py <repo_path> [--llm]"""
import sys
import requests

BASE = "http://localhost:8000"
QS = [
    "Explain the architecture of this project.",
    "How does the application start?",
    "Where is driver distraction detection implemented?",
    "Which port does the driver monitoring service use?",
    "Where is the blockchain implementation?",
]

r = requests.post(f"{BASE}/api/repo", json={"path": sys.argv[1]}).json()
print(r["name"], r["file_count"], "files", r["languages"])
for q in QS:
    print("\n=== Q:", q)
    a = requests.post(f"{BASE}/api/ask", json={"question": q}, timeout=300).json()
    print("mode:", a.get("mode"))
    for s in a["sources"]:
        print("  src:", s["file"], f"L{s['start_line']}-{s['end_line']}")
    if "--llm" in sys.argv:
        print("ANSWER:", a["answer"][:700])
