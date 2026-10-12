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
Prunes oversized tool outputs and recovers status back to `IDLE`:

```bash
# Heal all stuck or bloated sessions
python agydoc.py heal --all

# Or heal a specific session
python agydoc.py heal dd8201a0
```
```text
[+] Healing dd8201a0...
    - Cleared hanging errors : 1
    - Pruned tool outputs    : 38 steps (-728.5 KB)
    - Safety backup saved    : dd8201a0.db.bak_20261012_1145
    -> Recovered to IDLE state!
```

### 3. Rollback / Undo (`restore`)
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
