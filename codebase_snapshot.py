#!/usr/bin/env python3
"""Codebase snapshot for ClusterMind: collects diagnostics and file contents into one text file.

Run it from the project folder (the one that contains cmapp/ and cmbench/):

    python codebase_snapshot.py            # diagnostics + file tree + the UI files (small, good for UI problems)
    python codebase_snapshot.py --full     # diagnostics + tree + all source files (large)
    python codebase_snapshot.py --paths cmapp/web.py cmapp/static/app.css    # only the files you name

It writes snapshot_output.txt next to this script, and prints the diagnostics on screen.
Open snapshot_output.txt, copy everything, and paste it into the chat.

Safety: .env files are never read, and values on lines that look like secrets
(KEY / TOKEN / PASSWORD / SECRET) are masked. Models, data, runs and results are skipped.
"""
import argparse
import hashlib
import os
import platform
import re
import socket
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "snapshot_output.txt")

SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "node_modules", "models", "runs", "runs_rerun",
             "results", "results_rerun", "results_gui", "data", ".venv", "venv", "env", ".idea", ".vscode"}
TEXT_EXT = {".py", ".html", ".css", ".js", ".md", ".txt", ".yml", ".yaml", ".sh", ".toml", ".ini", ".cfg",
            ".json", ".example", ".gitignore", ".dockerignore"}
TEXT_NAMES = {"Dockerfile", "cm", "run.sh", "requirements.txt", ".env.example", ".gitignore", ".dockerignore"}
UI_FILES = ["cmapp/static/app.css", "cmapp/static/app.js", "cmapp/templates/index.html",
            "cmapp/web.py", "cmapp/__main__.py"]
MAX_FILE_BYTES = 80_000
MAX_TOTAL_BYTES = 600_000
SECRET_RE = re.compile(r"^(\s*[A-Za-z0-9_.-]*(KEY|TOKEN|PASSWORD|SECRET)[A-Za-z0-9_.-]*\s*[=:]\s*)(.+)$", re.I)

lines = []


def out(s=""):
    lines.append(s)


def rel(p):
    return os.path.relpath(p, ROOT).replace("\\", "/")


def sha(path):
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:12]
    except OSError:
        return "unreadable"


def read_text(path):
    with open(path, "rb") as f:
        data = f.read(MAX_FILE_BYTES + 1)
    truncated = len(data) > MAX_FILE_BYTES
    text = data[:MAX_FILE_BYTES].decode("utf-8", errors="replace")
    masked = []
    for ln in text.splitlines():
        m = SECRET_RE.match(ln)
        masked.append(m.group(1) + "***MASKED***" if m and m.group(3).strip() else ln)
    return "\n".join(masked), truncated


def is_text(name):
    if name in TEXT_NAMES:
        return True
    return os.path.splitext(name)[1].lower() in TEXT_EXT


def port_open(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.4):
            return True
    except OSError:
        return False


def diagnostics():
    out("=" * 78)
    out("CLUSTERMIND SNAPSHOT")
    out("=" * 78)
    out(f"Created     : {time.strftime('%Y-%m-%d %H:%M:%S')}")
    out(f"Project root: {ROOT}")
    out(f"Python      : {sys.version.split()[0]} ({platform.platform()})")
    out()
    out("-- UI file check (does your copy contain the new dark purple code?) --")
    checks = [
        ("cmapp/static/app.css", "e040fb", "dark purple accent colour"),
        ("cmapp/static/app.css", ".node-card", "node card styles"),
        ("cmapp/static/app.js", "node-card", "node card rendering"),
        ("cmapp/templates/index.html", "node-cards", "node card container"),
        ("cmapp/templates/index.html", "Cluster<span>Mind</span>", "new header"),
    ]
    for relpath, needle, label in checks:
        p = os.path.join(ROOT, relpath)
        if not os.path.isfile(p):
            out(f"  MISSING  {relpath}")
            continue
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            found = needle in f.read()
        out(f"  {'OK     ' if found else 'OLD    '} {relpath:32s} {label:28s} size={os.path.getsize(p):6d}  "
            f"modified={time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(os.path.getmtime(p)))}  sha={sha(p)}")
    out()
    out("-- Other copies of these files on disk (a second project folder can be the one actually served) --")
    found_any = False
    parent = os.path.dirname(ROOT)
    for dirpath, dirnames, filenames in os.walk(parent):
        depth = dirpath[len(parent):].count(os.sep)
        if depth > 3:
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        if "app.css" in filenames and os.path.basename(dirpath) == "static":
            p = os.path.join(dirpath, "app.css")
            if os.path.abspath(p) != os.path.abspath(os.path.join(ROOT, "cmapp/static/app.css")):
                out(f"  other copy: {p}  sha={sha(p)}")
                found_any = True
    if not found_any:
        out("  none found")
    out()
    out("-- What the Flask app will actually serve --")
    sys.path.insert(0, ROOT)
    try:
        import cmapp.web as w  # noqa: WPS433
        app = getattr(w, "app", None) or (w.create_app() if hasattr(w, "create_app") else None)
        if app is not None:
            out(f"  static folder  : {app.static_folder}")
            out(f"  template folder: {app.template_folder}")
            out(f"  jinja auto-reload: {app.config.get('TEMPLATES_AUTO_RELOAD')}")
        else:
            out("  could not locate the Flask app object in cmapp.web")
        out(f"  cmapp imported from: {os.path.dirname(os.path.abspath(w.__file__))}")
    except Exception as e:  # noqa: BLE001
        out(f"  could not import cmapp.web: {type(e).__name__}: {e}")
    out()
    out("-- Servers listening on common ports (an old server keeps serving the OLD page until restarted) --")
    for port in (8000, 8765, 5000, 8080):
        out(f"  port {port}: {'LISTENING' if port_open(port) else 'closed'}")
    out()
    out("If a UI file says OLD, copy the new file over it. If all say OK but the page looks old, stop the server")
    out("(Ctrl+C in its terminal), start it again, then hard-refresh the browser with Ctrl+F5.")
    out()


def tree():
    out("-" * 78)
    out("FILE TREE (models, data, runs, results are skipped)")
    out("-" * 78)
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        depth = rel(dirpath).count("/") + (0 if dirpath == ROOT else 1)
        indent = "  " * (0 if dirpath == ROOT else depth)
        if dirpath != ROOT:
            out(f"{indent[:-2]}{os.path.basename(dirpath)}/")
        for fn in sorted(filenames):
            p = os.path.join(dirpath, fn)
            out(f"{indent}{fn}  ({os.path.getsize(p)} bytes)")
    out()


def dump(paths):
    total = 0
    for p in paths:
        full = os.path.join(ROOT, p)
        if not os.path.isfile(full):
            out("-" * 78)
            out(f"FILE: {p}  (NOT FOUND)")
            continue
        if os.path.basename(p) == ".env":
            continue
        try:
            text, truncated = read_text(full)
        except OSError as e:
            out(f"FILE: {p}  (unreadable: {e})")
            continue
        if total + len(text) > MAX_TOTAL_BYTES:
            out("-" * 78)
            out(f"FILE: {p}  (skipped: total size limit reached; run again with --paths for this file)")
            continue
        total += len(text)
        out("-" * 78)
        out(f"FILE: {p}   size={os.path.getsize(full)} bytes   sha={sha(full)}" + ("   [TRUNCATED]" if truncated else ""))
        out("-" * 78)
        out(text)
        out()


def all_text_files():
    found = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for fn in sorted(filenames):
            if fn in ("snapshot_output.txt", "codebase_snapshot.py", ".env"):
                continue
            if is_text(fn):
                found.append(rel(os.path.join(dirpath, fn)))
    return found


def main():
    ap = argparse.ArgumentParser(description="Create snapshot_output.txt for pasting into the chat.")
    ap.add_argument("--full", action="store_true", help="include all source files (large)")
    ap.add_argument("--paths", nargs="+", help="include only these files (relative paths)")
    args = ap.parse_args()

    diagnostics()
    tree()
    if args.paths:
        dump([p.replace("\\", "/") for p in args.paths])
    elif args.full:
        dump(all_text_files())
    else:
        dump(UI_FILES)

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    # Print only the diagnostics block to the screen.
    end = next((i for i, l in enumerate(lines) if l.startswith("FILE TREE")), len(lines))
    print("\n".join(lines[:max(end - 1, 0)]))
    print(f"\nWrote {OUT} ({os.path.getsize(OUT)} bytes). Open it, copy everything, and paste it into the chat.")


if __name__ == "__main__":
    main()