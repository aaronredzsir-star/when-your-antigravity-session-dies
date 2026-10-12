# 🩺 Antigravity Doctor (`agydoc`)

> Automatic context hygiene, payload pruning, and crash recovery for Google Antigravity. Zero dependencies.

## Why?

Long sessions accumulate heavy tool outputs (`view_file`, terminal dumps) in local SQLite, causing prefill delays, gateway timeouts (`stream interrupted / EOF`), and 10-minute retry deadlocks. `agydoc` safely prunes bloated tool outputs—unlocking sessions while keeping 100% of user prompts, assistant reasoning, and code diffs intact.

---

## ⚡ Quickstart

Requires Python 3.8+ (no dependencies).

```bash
git clone https://github.com/aaronredzsir-star/when-your-antigravity-session-dies.git
cd when-your-antigravity-session-dies
```

---

## 🤖 Automatic Modes (Set-and-Forget)

### Option A: Install Native Antigravity Plugin (Recommended)

Installs directly into `~/.gemini/config/plugins/antigravity-doctor`:

```bash
python agydoc.py install-plugin
```

* **PreInvocation Hook**: Runs before every model turn; auto-prunes historical tool bloat if it exceeds safe thresholds to prevent gateway timeouts.
* **Stop Hook**: Automatically clears hanging error loops if a connection drops, keeping sessions in `IDLE` state.
* *(To uninstall: `python agydoc.py uninstall-plugin`)*

### Option B: Run Background Watcher Daemon

Continuously monitors session databases and automatically rescues stuck sessions:

```bash
python agydoc.py watch
```

```text
[*] Antigravity Doctor Watcher started (interval: 15s).
[14:51:25] [!] Auto-healing session d01d9544 (MAP复现与知识图谱可视化)...
           -> Rescued! Pruned 8 steps (-98.4 KB). State is now IDLE.
```

---

## 🛠️ Manual CLI Usage & Examples

### 1. Diagnose Sessions (`scan`)
Find which conversations are deadlocked or bloated:

```bash
python agydoc.py scan
```
```text
ID (Short)   Status   Size     Steps  Health
-----------  -------  -------  -----  -----------
dd8201a0...  RUNNING  36.4 MB  2191   [!] BRICKED
d01d9544...  IDLE     32.2 MB  882    [?] BLOATED
b06a3eb7...  IDLE     1.2 MB   45     [✓] HEALTHY
```

### 2. Heal Sessions Manually (`heal`)
Cleans hanging retry loops and auto-compacts bloated context:

```bash
# Heal all stuck or warning sessions
python agydoc.py heal --all

# Or heal a specific session
python agydoc.py heal dd8201a0
```
```text
[+] Healing dd8201a0...
    - Removed hanging errors : 2
    - Post-checkpoint size   : 485.2 KB
    - Auto-compacted         : Yes (Checkpoint synthesized)
    - Database integrity     : ok
    - Safety backup saved to : dd8201a0.db.bak_20261013_0410
    -> Session successfully recovered to IDLE state!
```

### 3. Native Compaction (`compact`)
Antigravity lacks a manual `/compact` command. When tool chains accumulate massive unpruned context, subsequent model calls can time out at the 60s gateway limit. `agydoc compact` synthesizes a native Checkpoint (`step_type = 23`), resetting active LLM prefill context to ~15 KB while leaving 100% of past SQLite steps intact:

```bash
python agydoc.py compact d01d9544
```
```text
[*] Synthesizing native checkpoint for d01d9544...
[+] Successfully synthesized native Checkpoint at Step 3311!
    - Checkpoint payload size: 79816 bytes
    - Database integrity     : ok
    -> LLM active prefill context reset to ~15 KB. Zero gateway timeout risk!
```

### 4. Rollback / Undo (`restore`)
Every operation creates an automatic timestamped backup. Revert anytime:

```bash
python agydoc.py restore dd8201a0
```
```text
[+] Restored dd8201a0 from backup dd8201a0.db.bak_20261012_1145
```

---

## 📄 License

MIT
