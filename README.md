# 🩺 Antigravity Doctor (`agydoc`)

> **Context hygiene, payload pruning, and crash recovery toolkit for Google Antigravity.**
> *Rescue bricked conversations, fix the 10-minute retry loop, and keep mature agent sessions fast and healthy.*

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.8+](https://img.shields.io/badge/Python-3.8%2B-green.svg)](https://python.org)
[![Zero Dependencies](https://img.shields.io/badge/Dependencies-Zero-brightgreen.svg)]()

---

## 🎯 The Problem: Why Do Long Antigravity Sessions Die?

When developing complex, multi-day projects with **Google Antigravity**, users frequently encounter this failure mode:

1. **Unpruned Context Bloat**: Every tool execution (`view_file`, `run_command` logs, terminal outputs) is appended verbatim into the local SQLite trajectory. A session can easily balloon to hundreds of kilobytes or megabytes of raw protobuf payload (150k+ tokens).
2. **The Cache Cliff & Zero-Byte Starvation**: Once the server's ephemeral prompt cache expires, the model is forced into full prefill on the entire monolithic history. During the 40~60s of silence while the model precomputes and thinks, **zero keep-alive bytes are streamed back**.
3. **The Gateway Cutoff**: Google's API gateway naturally terminates the idle connection after ~60s (`The stream was interrupted`).
4. **The 10-Minute Retry Hell**: The client blind-spams the exact same bloated payload for 9 attempts into a severed session, ending in an unhandled `EOF`:
   ```
   4s → 5s → 15s → 28s → 58s → 1m26s → 2m29s → 3m41s
   ```
5. **The Compaction Deadlock**: Auto-compaction only triggers upon completing a turn. Because the turn crashes mid-flight, **compaction never fires**. And because Antigravity has no manual `/compact` command, the session becomes permanently bricked.

---

## 🚀 How `agydoc` Solves It

`agydoc` is a zero-dependency, standalone tool that performs precision surgery on your local Antigravity databases (`~/.gemini/antigravity` & `~/.gemini/antigravity-ide`):

* 🔍 **Smart Diagnostics (`scan`)**: Instantly inspects all local sessions, evaluates context bloat, detects stuck `RUNNING` locks, and flags sessions in active error loops.
* ✂️ **In-Place Protobuf Tool Pruning (`heal`)**: Parses raw binary protobuf payloads without external dependencies. It selectively truncates historical, repetitive tool outputs (`view_file` source dumps, giant logs) down to compact indices, **reclaiming up to 70%+ of payload size while 100% preserving user prompts, reasoning chains, and code diffs**.
* 🔓 **State Unlock**: Rolls back trailing orphaned EOF errors and resets deadlocked `CASCADE_RUN_STATUS_RUNNING` states back to `IDLE`.
* 🛡️ **Safety First**: Every modification creates an automatic timestamped cold backup (`.bak_<timestamp>`), with a 1-second `restore` command.

---

## 📦 Quickstart

### Option 1: Run directly (No installation required)

Just run `agydoc.py` with Python 3:

```bash
# 1. Scan and diagnose all conversations
python agydoc.py scan

# 2. Heal all bricked or bloated conversations
python agydoc.py heal --all

# 3. Heal a specific conversation
python agydoc.py heal <session-id>
```

### Option 2: Install as a global CLI

```bash
git clone https://github.com/aaronredzsir-star/when-your-antigravity-session-dies.git
cd when-your-antigravity-session-dies
pip install -e .

# Now use `agydoc` anywhere!
agydoc scan
agydoc heal --all
```

---

## 🖥️ CLI Usage

### 1. Scan Sessions (`agydoc scan`)

Diagnoses the health of all sessions across standalone Antigravity and Antigravity IDE:

```text
[*] Scanning Antigravity sessions...

ID (Short)   Status  Size     Steps  Health       Title / Note                  
-----------  ------  -------  -----  -----------  ------------------------------
b06a3eb7...  IDLE    96.7 MB  15004  [?] WARNING  Project Docs Review
dd8201a0...  RUNNING 36.4 MB  2191   [!] BRICKED  Map Visualization
d01d9544...  IDLE    32.2 MB  882    [?] WARNING  Gene Expression Engine
...
Total: 24 sessions | Bricked: 6 | Warning: 15
```

### 2. Heal Sessions (`agydoc heal`)

Recovers bricked sessions and prunes accumulated payload weight:

```text
agydoc heal --all
```

Output:
```text
[*] Found 6 session(s) to heal:
[+] Healing dd8201a0...
    - Removed hanging errors : 1
    - Pruned bloated steps   : 38
    - Reclaimed payload size : 728.5 KB
    - Database integrity     : ok
    - Safety backup saved to : ~/.gemini/antigravity/conversations/dd8201a0.db.bak_20261012_1145
    -> Session successfully recovered to IDLE state!
```

### 3. Rollback / Restore (`agydoc restore`)

If you ever want to revert a healed session back to its original state:

```bash
agydoc restore <session-id>
```

---

## 🛡️ Safety & Architecture

* **Zero External Dependencies**: Uses only standard Python modules (`sqlite3`, `pathlib`, `shutil`, `argparse`).
* **Non-Destructive**: Never deletes user messages, assistant thinking, or project decisions. Only prunes historical tool execution responses (`Field 140 Subfield 2`).
* **Cross-Platform**: Works identically on Windows (`C:\Users\<user>\.gemini`), macOS (`~/.gemini`), and Linux.

---

## 📄 License

MIT License. Contributions, issues, and PRs are welcome!
