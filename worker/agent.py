#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Brute Worker — pulls jobs from Firestore and runs them locally through hashcat.

Runs on the GPU machine (the "worker"). Dictionaries and rules stay only
here — only their names (metadata) are published to Firestore, never their
contents.

Settings live in config.json next to this file (or next to BruteWorker.exe,
if running as a built exe). On first run, config.json is created
automatically with default values — edit it and run the worker again.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time

import firebase_admin
from firebase_admin import credentials, firestore

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def base_dir() -> str:
    """Folder next to the script, or next to the exe if built with PyInstaller."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


CONFIG_PATH = os.path.join(base_dir(), "config.json")

DEFAULT_CONFIG = {
    "hashcat_path": r"C:\hashcat\hashcat.exe",
    "credentials_path": r"C:\brute\firebase-credentials.json",
    "project_id": "brute-me",
    "dict_dir": r"C:\dicts",
    "rule_dir": r"C:\rules",
    "poll_interval_seconds": 30,
    "metadata_update_interval_seconds": 3600,
}


def load_config() -> dict:
    if not os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2, ensure_ascii=False)
        print(f"[SETUP] Config file created: {CONFIG_PATH}")
        print("[SETUP] Fill in the paths to hashcat.exe, the Firebase key, dictionaries and rules,")
        print("[SETUP] then run the worker again.")
        sys.exit(0)

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = dict(DEFAULT_CONFIG)
        cfg.update(json.load(f))
        return cfg


CFG = load_config()

HASHCAT_PATH = CFG["hashcat_path"]
CRED_PATH = CFG["credentials_path"]
PROJECT_ID = CFG["project_id"]
DICT_BASE = CFG["dict_dir"]
RULE_BASE = CFG["rule_dir"]
POLL_INTERVAL = CFG["poll_interval_seconds"]
METADATA_UPDATE_INTERVAL = CFG["metadata_update_interval_seconds"]


def check_prerequisites() -> None:
    problems = []
    if not os.path.isfile(HASHCAT_PATH):
        problems.append(f"hashcat not found at: {HASHCAT_PATH}")
    if not os.path.isfile(CRED_PATH):
        problems.append(f"Firebase credentials not found: {CRED_PATH}")
    if not os.path.isdir(DICT_BASE):
        problems.append(f"dictionary folder not found: {DICT_BASE} (will be created empty)")
        os.makedirs(DICT_BASE, exist_ok=True)
    if not os.path.isdir(RULE_BASE):
        problems.append(f"rule folder not found: {RULE_BASE} (will be created empty)")
        os.makedirs(RULE_BASE, exist_ok=True)

    if problems:
        print("[SETUP] Check config.json:")
        for p in problems:
            print(f"  - {p}")
        if not os.path.isfile(HASHCAT_PATH) or not os.path.isfile(CRED_PATH):
            sys.exit(1)


# ---------------------------------------------------------------------------
# Scanning dictionaries and rules
# ---------------------------------------------------------------------------

def scan_dicts() -> dict:
    dicts = {}
    if not os.path.exists(DICT_BASE):
        return dicts
    for item in os.listdir(DICT_BASE):
        full_path = os.path.join(DICT_BASE, item)
        if os.path.isdir(full_path):
            files = [
                os.path.join(full_path, f)
                for f in os.listdir(full_path)
                if os.path.isfile(os.path.join(full_path, f))
            ]
            if files:
                dicts[item] = files
        elif os.path.isfile(full_path):
            dicts[item] = [full_path]
    return dicts


def scan_rules() -> dict:
    rules = {}
    if not os.path.exists(RULE_BASE):
        return rules
    for item in os.listdir(RULE_BASE):
        full_path = os.path.join(RULE_BASE, item)
        if os.path.isfile(full_path) and item.endswith(".rule"):
            rules[item] = full_path
    rules["none"] = ""
    return rules


def update_metadata(db) -> tuple:
    dicts = scan_dicts()
    rules = scan_rules()
    dict_list = [
        {"name": name, "type": "folder" if len(paths) > 1 else "file"}
        for name, paths in dicts.items()
    ]
    rule_list = [{"name": name} for name in rules.keys()]
    doc_ref = db.collection("metadata").document("dictionary_rules")
    doc_ref.set(
        {
            "dicts": dict_list,
            "rules": rule_list,
            "updated_at": firestore.SERVER_TIMESTAMP,
        }
    )
    print(f"[META] Updated: {len(dict_list)} dictionaries, {len(rule_list)} rules")
    return dicts, rules


# ---------------------------------------------------------------------------
# Running hashcat
# ---------------------------------------------------------------------------

def _run_hashcat(cmd: list, hash_file: str, out_file: str, task_ref=None) -> str | None:
    """Runs hashcat, optionally allowing the job to be cancelled (task_ref)."""
    hashcat_dir = os.path.dirname(HASHCAT_PATH)
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        cwd=hashcat_dir,
        encoding="utf-8",
        errors="replace",
    )

    cancelled = False
    while proc.poll() is None:
        if task_ref is not None:
            snap = task_ref.get()
            if snap.exists and snap.to_dict().get("status") == "cancelling":
                proc.kill()
                cancelled = True
                break
        time.sleep(2)

    password = None
    if not cancelled and os.path.exists(out_file):
        with open(out_file, "r", encoding="utf-8", errors="replace") as f:
            content = f.read().strip()
            if content and not content.startswith("Status"):
                password = content

    for f in (hash_file, out_file):
        try:
            os.unlink(f)
        except OSError:
            pass

    if cancelled:
        return "__CANCELLED__"
    return password


def run_hashcat_single(hash_content: str, dict_path: str, rule_path: str, mode: str, task_ref=None):
    fd, hash_file = tempfile.mkstemp(suffix=".hc22000", text=True)
    os.close(fd)
    with open(hash_file, "w", encoding="utf-8") as f:
        f.write(hash_content)

    fd, out_file = tempfile.mkstemp(suffix=".out", text=True)
    os.close(fd)

    cmd = [
        HASHCAT_PATH,
        "-m", mode,
        "-a", "0",
        "-w", "3",
        "-o", out_file,
        "--outfile-format", "2",
        "--potfile-disable",
        hash_file,
        dict_path,
    ]
    if rule_path:
        cmd += ["-r", rule_path]

    print(f"[HASHCAT] {' '.join(cmd)}")
    return _run_hashcat(cmd, hash_file, out_file, task_ref)


def run_mask_attack(hash_content: str, mask_pattern: str, mode: str, task_ref=None):
    fd, hash_file = tempfile.mkstemp(suffix=".hc22000", text=True)
    os.close(fd)
    with open(hash_file, "w", encoding="utf-8") as f:
        f.write(hash_content)

    fd, out_file = tempfile.mkstemp(suffix=".out", text=True)
    os.close(fd)

    cmd = [
        HASHCAT_PATH,
        "-m", mode,
        "-a", "3",
        "-w", "3",
        "-o", out_file,
        "--outfile-format", "2",
        "--potfile-disable",
        hash_file,
        mask_pattern,
    ]
    print(f"[HASHCAT] mask: {' '.join(cmd)}")
    return _run_hashcat(cmd, hash_file, out_file, task_ref)


def run_on_dict_folder(hash_content: str, file_list: list, rule_path: str, mode: str, task_ref=None):
    for single_dict in file_list:
        print(f"  -> {single_dict}")
        password = run_hashcat_single(hash_content, single_dict, rule_path, mode, task_ref)
        if password:
            return password
    return None


def detect_hash_mode(hash_content: str) -> str:
    if "*" in hash_content and "PMKID" in hash_content:
        return "22000"
    elif "WPA" in hash_content and "EAPOL" in hash_content:
        return "2500"
    return "22000"


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("Brute Worker")
    print(f"hashcat: {HASHCAT_PATH}")
    print(f"Polling the queue every {POLL_INTERVAL}s")
    check_prerequisites()

    cred = credentials.Certificate(CRED_PATH)
    firebase_admin.initialize_app(cred)
    db = firestore.client()

    dicts, rules = update_metadata(db)
    last_metadata_update = time.time()

    print("Waiting for jobs...")
    print("=" * 60)

    while True:
        try:
            if time.time() - last_metadata_update > METADATA_UPDATE_INTERVAL:
                dicts, rules = update_metadata(db)
                last_metadata_update = time.time()

            pending_query = db.collection("tasks").where("status", "==", "pending").limit(1)
            docs = list(pending_query.stream())
            if not docs:
                time.sleep(POLL_INTERVAL)
                continue

            doc = docs[0]
            task = doc.to_dict()
            task_id = doc.id
            attack_mode = task.get("attack_mode", "dict")
            print(f"\n[TASK {task_id}] Mode: {attack_mode}")

            doc.reference.update({"status": "running", "progress": 0})

            mode = detect_hash_mode(task.get("hash", ""))
            print(f"  Hash mode: {mode}")

            password = None
            if attack_mode == "mask":
                mask = task.get("mask")
                if not mask:
                    doc.reference.update({"status": "failed", "error": "No mask pattern", "progress": 100})
                    continue
                print(f"  Mask: {mask}")
                password = run_mask_attack(task["hash"], mask, mode, doc.reference)
            else:
                dict_name = task.get("dict")
                rule_name = task.get("rule", "none")
                if dict_name not in dicts:
                    doc.reference.update(
                        {"status": "failed", "error": f"Dictionary not found: {dict_name}", "progress": 100}
                    )
                    continue
                if rule_name not in rules:
                    doc.reference.update(
                        {"status": "failed", "error": f"Rule not found: {rule_name}", "progress": 100}
                    )
                    continue
                dict_files = dicts[dict_name]
                rule_path = rules[rule_name]
                password = run_on_dict_folder(task["hash"], dict_files, rule_path, mode, doc.reference)

            if password == "__CANCELLED__":
                print("  [CANCELLED]")
                doc.reference.update({"status": "cancelled", "progress": 100})
            elif password:
                print(f"  [SUCCESS] Password: {password}")
                doc.reference.update(
                    {
                        "status": "completed",
                        "result": password,
                        "progress": 100,
                        "finished_at": firestore.SERVER_TIMESTAMP,
                    }
                )
            else:
                print("  [NOT FOUND]")
                doc.reference.update(
                    {
                        "status": "failed",
                        "error": "Password not found" if attack_mode == "mask" else "Not found in dictionary",
                        "progress": 100,
                        "finished_at": firestore.SERVER_TIMESTAMP,
                    }
                )
        except Exception as e:  # noqa: BLE001 - the worker should survive a single error and keep polling
            print(f"[ERROR] {e}")
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
