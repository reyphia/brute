#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Brute Panel — a desktop wrapper around the built web UI (the build/ folder).

Starts a local web server on 127.0.0.1 and opens it in a native window via
pywebview. Doesn't talk to anything outside except Firebase (from the browser
context).

This file gets turned into panel\\dist\\BrutePanel.exe by build_exe.bat.
"""

import http.server
import os
import socketserver
import sys
import threading

import webview

PORT = 8765


def resource_dir():
    """Folder containing build/ — both for a normal run and inside the .exe (PyInstaller)."""
    if getattr(sys, "frozen", False):
        return sys._MEIPASS  # temp folder PyInstaller unpacks --add-data into
    return os.path.dirname(os.path.abspath(__file__))


def serve_build_folder(build_dir: str, port: int):
    handler_cls = http.server.SimpleHTTPRequestHandler

    class Handler(handler_cls):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=build_dir, **kwargs)

        def log_message(self, format, *args):
            pass  # keep the console quiet

    with socketserver.TCPServer(("127.0.0.1", port), Handler) as httpd:
        httpd.serve_forever()


def main():
    build_dir = os.path.join(resource_dir(), "build")
    if not os.path.isdir(build_dir):
        print(
            "Couldn't find a build/ folder next to the app.\n"
            "Run `npm run build` to build the web UI before building the .exe "
            "(build_exe.bat already does this for you)."
        )
        input("Press Enter to exit...")
        sys.exit(1)

    server_thread = threading.Thread(
        target=serve_build_folder, args=(build_dir, PORT), daemon=True
    )
    server_thread.start()

    webview.create_window(
        "Brute — Panel",
        f"http://127.0.0.1:{PORT}",
        width=1150,
        height=820,
        min_size=(700, 500),
    )
    webview.start()


if __name__ == "__main__":
    main()
