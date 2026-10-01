"""Bundle the FastAPI backend into backend/dist/localrepo-backend/ with PyInstaller."""
import os
import subprocess
import sys

here = os.path.dirname(os.path.abspath(__file__))
backend = os.path.normpath(os.path.join(here, "..", "backend"))
subprocess.check_call([
    sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir",
    "--name", "localrepo-backend", "--exclude-module", "tkinter",
    "--distpath", os.path.join(backend, "dist"),
    "--workpath", os.path.join(backend, "build"),
    "--specpath", os.path.join(backend, "build"),
    os.path.join(backend, "server.py"),
], cwd=backend)
