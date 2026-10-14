# 🩺 Antigravity Doctor (`agydoc`)

> Proactive context hygiene, native checkpoint compaction, and crash recovery for Google Antigravity. Zero dependencies.

## Why?

Long sessions accumulate heavy tool outputs (`view_file`, terminal dumps) in local SQLite. When post-checkpoint context exceeds ~150–200 KB, API calls hit Google's 60-second gateway streaming timeout (`stream interrupted / EOF`), triggering endless retry loops and permanently locking sessions in `RUNNING`.

`agydoc` provides **proactive pre-flight compaction** and **non-destructive native checkpoint synthesis**—permanently eliminating timeouts while preserving 100% of user prompts, assistant reasoning, and code diffs.

---

## ⚡ Quickstart

Requires Python 3.8+ (no dependencies).

```bash
git clone https://github.com/aaronredzsir-star/when-your-antigravity-session-dies.git
cd when-your-antigravity-session-dies
```

---

## 🤖 Automatic Protection (Set-and-Forget)

### Option A: Install Native Antigravity Plugin (Recommended)

Installs directly into `~/.gemini/config/plugins/antigravity-doctor`:

```bash
python agydoc.py install-plugin
```

* **PreInvocation Hook (Proactive Immune System)**: Runs *before* LLM prefill starts. If uncompacted tool payload exceeds 200 KB, it proactively synthesizes a native Checkpoint while preserving the active user prompt at the tip. Prefill payload drops to ~18 KB (1.5s latency), **completely preventing 60s gateway timeouts before they happen**.
* **Stop Hook (Emergency Recovery)**: Cleans trailing interrupted retry loops (alternating 17/15 steps) if an unexpected disconnect occurs, unlocking the session back to `IDLE`.
* *(To uninstall: `python agydoc.py uninstall-plugin`)*

### Option B: Run Background Watcher Daemon

Continuously monitors session databases and automatically rescues stuck or bloated sessions:

```bash
python agydoc.py watch
```

```text
[*] Antigravity Doctor Watcher started (interval: 15s).
[14:51:25] [!] Auto-healing session d01d9544 (MAP复现与知识图谱可视化)...
           -> Rescued! Synthesized Checkpoint at Step 4046. State is now IDLE.
```

---

## 🛠️ Manual CLI Usage & Examples

### 1. Diagnose Sessions (`scan`)
Find which conversations are deadlocked or suffering from post-checkpoint bloat:

```bash
python agydoc.py scan
```
```text
ID (Short)   Status   Size     Steps  Post-Ckp   Health       Title / Note
-----------  -------  -------  -----  ---------  -----------  --------------------------
d01d9544...  RUNNING  48.8 MB  4033   1053.2 KB  [!] BRICKED  MAP复现与知识图谱可视化
f8396401...  IDLE     12.0 MB  1865   0.0 KB     [+] OK       Untitled
b06a3eb7...  IDLE     72.5 MB  15004  889.2 KB   [?] WARNING  阅读项目文档
```

### 2. Native Compaction (`compact`)
Antigravity lacks a manual `/compact` command. `agydoc compact` synthesizes a native Antigravity Checkpoint (`step_type = 23`), resetting active LLM prefill weight from ~1 MB to ~15 KB while leaving 100% of historical SQLite steps intact:

```bash
python agydoc.py compact d01d9544
```
```text
[*] Synthesizing native checkpoint for d01d9544...
[+] Successfully synthesized native Checkpoint at Step 4046!
    - Checkpoint payload size: 103570 bytes
    - Preserved active prompt: Yes (at Step 4047)
    - Database integrity     : ok
    -> LLM active prefill context reset to ~18 KB. Zero gateway timeout risk!
```

### 3. Heal Sessions Manually (`heal`)
Cleans hanging retry loops, resets status locks, and auto-compacts context if bloated:

```bash
# Heal all stuck or warning sessions
python agydoc.py heal --all

# Or heal a specific session
python agydoc.py heal dd8201a0
```
```text
[+] Healing dd8201a0...
    - Removed hanging errors : 3
    - Post-checkpoint size   : 485.2 KB
    - Auto-compacted         : Yes (Checkpoint synthesized)
    - Database integrity     : ok
    - Safety backup saved to : dd8201a0.db.bak_20261014_1849
    -> Session successfully recovered to IDLE state!
```

### 4. Rollback / Undo (`restore`)
Every operation creates an automatic timestamped backup. Revert anytime:

```bash
python agydoc.py restore dd8201a0
```
```text
[+] Restored dd8201a0 from backup dd8201a0.db.bak_20261014_1849
```

---

## 🧪 Testing

Run the automated test suite:

```bash
python -m unittest tests/test_core.py
```

---

## 📄 License

MIT
