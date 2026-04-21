#!/usr/bin/env python3
"""
BTC Trading System Dashboard Launcher
Starts both the FastAPI backend and serves the Next.js frontend.
"""
import subprocess
import sys
import os
import time
import signal

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_PYTHON = os.path.join(BASE_DIR, "venv", "bin", "python3.14")

def start_backend():
    """Start the FastAPI backend server."""
    print("[1/2] Starting FastAPI backend on http://localhost:8000 ...")
    proc = subprocess.Popen(
        [VENV_PYTHON, "-m", "uvicorn", "dashboard_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"],
        cwd=BASE_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    # Wait for startup
    for line in proc.stdout:
        print(f"  [API] {line.rstrip()}")
        if "Application startup complete" in line:
            break
    return proc

def start_frontend():
    """Serve the built Next.js frontend."""
    print("[2/2] Starting Next.js frontend on http://localhost:3000 ...")
    proc = subprocess.Popen(
        ["npx", "serve@latest", "dist", "-l", "3000"],
        cwd=os.path.join(BASE_DIR, "dashboard"),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    time.sleep(2)
    return proc

def main():
    print("=" * 60)
    print("  BTC Trading System Dashboard")
    print("=" * 60)
    print()

    backend = start_backend()
    frontend = start_frontend()

    print()
    print("Dashboard is running!")
    print("  Frontend: http://localhost:3000")
    print("  API:      http://localhost:8000")
    print("  API Docs: http://localhost:8000/docs")
    print()
    print("Press Ctrl+C to stop.")
    print()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        backend.terminate()
        frontend.terminate()
        backend.wait(timeout=5)
        frontend.wait(timeout=5)
        print("Done.")

if __name__ == "__main__":
    main()
