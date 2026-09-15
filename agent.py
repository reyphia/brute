#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import tempfile
import subprocess
import re
from datetime import datetime

import firebase_admin
from firebase_admin import credentials, firestore

# ========= НАСТРОЙКИ =========
HASHCAT_PATH = r"C:\hashcat\hashcat.exe"
CRED_PATH = r"E:\cracker_agent\brute-me-firebase-adminsdk-fbsvc-bba53e05a3.json"
PROJECT_ID = "brute-me"

DICT_BASE = r"E:\dicts"
RULE_BASE = r"E:\rules"

POLL_INTERVAL = 30
METADATA_UPDATE_INTERVAL = 3600
# =============================

def scan_dicts():
    dicts = {}
    if not os.path.exists(DICT_BASE):
        return dicts
    for item in os.listdir(DICT_BASE):
        full_path = os.path.join(DICT_BASE, item)
        if os.path.isdir(full_path):
            files = [os.path.join(full_path, f) for f in os.listdir(full_path) if os.path.isfile(os.path.join(full_path, f))]
            if files:
                dicts[item] = files
        elif os.path.isfile(full_path):
            dicts[item] = [full_path]
    return dicts

def scan_rules():
    rules = {}
    if not os.path.exists(RULE_BASE):
        return rules
    for item in os.listdir(RULE_BASE):
        full_path = os.path.join(RULE_BASE, item)
        if os.path.isfile(full_path) and item.endswith('.rule'):
            rules[item] = full_path
    rules["none"] = ""
    return rules

def update_metadata(db):
    dicts = scan_dicts()
    rules = scan_rules()
    dict_list = [{"name": name, "type": "folder" if len(paths) > 1 else "file"} for name, paths in dicts.items()]
    rule_list = [{"name": name} for name in rules.keys()]
    doc_ref = db.collection("metadata").document("dictionary_rules")
    doc_ref.set({
        "dicts": dict_list,
        "rules": rule_list,
        "updated_at": firestore.SERVER_TIMESTAMP
    })
    print(f"Metadata updated: {len(dict_list)} dicts, {len(rule_list)} rules")
    return dicts, rules

def run_hashcat_single(hash_content, dict_path, rule_path, mode):
    fd, hash_file = tempfile.mkstemp(suffix=".hc22000", text=True)
    os.close(fd)
    with open(hash_file, "w", encoding='utf-8') as f:
        f.write(hash_content)

    fd, out_file = tempfile.mkstemp(suffix=".out", text=True)
    os.close(fd)

    hashcat_dir = os.path.dirname(HASHCAT_PATH)
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

    print(f"[HASHCAT] Running: {' '.join(cmd)}")
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        cwd=hashcat_dir,
        encoding='utf-8',
        errors='replace'
    )
    proc.wait()

    password = None
    if os.path.exists(out_file):
        with open(out_file, "r", encoding='utf-8', errors='replace') as f:
            content = f.read().strip()
            if content and not content.startswith("Status"):
                password = content
    for f in [hash_file, out_file]:
        try:
            os.unlink(f)
        except:
            pass
    return password

def run_mask_attack(hash_content, mask_pattern, mode):
    fd, hash_file = tempfile.mkstemp(suffix=".hc22000", text=True)
    os.close(fd)
    with open(hash_file, "w", encoding='utf-8') as f:
        f.write(hash_content)

    fd, out_file = tempfile.mkstemp(suffix=".out", text=True)
    os.close(fd)

    hashcat_dir = os.path.dirname(HASHCAT_PATH)
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
    print(f"[HASHCAT] Mask attack: {' '.join(cmd)}")
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        cwd=hashcat_dir,
        encoding='utf-8',
        errors='replace'
    )
    proc.wait()

    password = None
    if os.path.exists(out_file):
        with open(out_file, "r", encoding='utf-8', errors='replace') as f:
            content = f.read().strip()
            if content and not content.startswith("Status"):
                password = content
    for f in [hash_file, out_file]:
        try:
            os.unlink(f)
        except:
            pass
    return password

def run_on_dict_folder(hash_content, file_list, rule_path, mode):
    for single_dict in file_list:
        print(f"  Trying: {single_dict}")
        password = run_hashcat_single(hash_content, single_dict, rule_path, mode)
        if password:
            return password
    return None

def detect_hash_mode(hash_content):
    if "*" in hash_content and "PMKID" in hash_content:
        return "22000"
    elif "WPA" in hash_content and "EAPOL" in hash_content:
        return "2500"
    else:
        return "22000"

def main():
    print("=" * 60)
    print("WPA2 Cracker Agent (mask attack support)")
    print(f"Hashcat: {HASHCAT_PATH}")
    print(f"Poll interval: {POLL_INTERVAL}s")

    cred = credentials.Certificate(CRED_PATH)
    firebase_admin.initialize_app(cred)
    db = firestore.client()

    dicts, rules = update_metadata(db)
    last_metadata_update = time.time()

    print("Waiting for tasks...")
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
            print(f"\n[TASK {task_id}] Attack mode: {task.get('attack_mode', 'dict')}")

            doc.reference.update({"status": "running", "progress": 0})

            mode = detect_hash_mode(task.get("hash", ""))
            print(f"  Hash mode: {mode}")

            password = None
            attack_mode = task.get('attack_mode', 'dict')
            if attack_mode == 'mask':
                mask = task.get('mask')
                if not mask:
                    doc.reference.update({"status": "failed", "error": "No mask pattern", "progress": 100})
                    continue
                print(f"  Mask pattern: {mask}")
                password = run_mask_attack(task['hash'], mask, mode)
            else:
                dict_name = task.get('dict')
                rule_name = task.get('rule', 'none')
                if dict_name not in dicts:
                    doc.reference.update({"status": "failed", "error": f"Dict {dict_name} not found", "progress": 100})
                    continue
                if rule_name not in rules:
                    doc.reference.update({"status": "failed", "error": f"Rule {rule_name} not found", "progress": 100})
                    continue
                dict_files = dicts[dict_name]
                rule_path = rules[rule_name]
                password = run_on_dict_folder(task['hash'], dict_files, rule_path, mode)

            if password:
                print(f"  [SUCCESS] Password: {password}")
                doc.reference.update({
                    "status": "completed",
                    "result": password,
                    "progress": 100,
                    "finished_at": firestore.SERVER_TIMESTAMP
                })
            else:
                print("  [FAILED] Password not found")
                doc.reference.update({
                    "status": "failed",
                    "error": "Password not found" if attack_mode == 'mask' else "Not found in dictionary",
                    "progress": 100,
                    "finished_at": firestore.SERVER_TIMESTAMP
                })
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()