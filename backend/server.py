"""Entry point for the packaged backend: python server.py --port 8123 [--static DIR]."""
import argparse
import os

import uvicorn

from main import app

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--static", default=None)
    args = ap.parse_args()
    if args.static:
        os.environ["LOCALREPO_STATIC"] = args.static
        # main.py mounts static files at import time, so mount here if import already happened
        from fastapi.staticfiles import StaticFiles
        if not any(getattr(r, "name", "") == "ui" for r in app.routes):
            app.mount("/", StaticFiles(directory=args.static, html=True), name="ui")
    # localhost only: never exposed to the network
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
