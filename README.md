# LocalRepo AI
Understand your codebase. Keep your code local.

Run (Ollama must be running with `gemma3:1b`):

    cd backend  && pip install -r requirements.txt && python -m uvicorn main:app --port 8000
    cd frontend && npm install && npm run dev      # http://localhost:5173

Paste a local repo path, click Load, and ask questions. Retrieval is keyword/filename/symbol based
(no embeddings); only the top matching chunks go to Ollama at localhost:11434.
