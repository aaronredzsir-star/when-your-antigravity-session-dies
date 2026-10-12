# 🩺 Antigravity Doctor (`agydoc`)

> Quick, zero-dependency CLI to rescue bricked Google Antigravity sessions and fix the 10-minute retry loop.

## Why?

Long sessions accumulate heavy tool outputs in local SQLite, triggering gateway timeouts and endless retry loops. `agydoc` safely prunes bloated historical tool outputs—unlocking the session while keeping 100% of your prompts, thoughts, and diffs intact.

---

## ⚡ Quickstart

Requires Python 3.8+ (no dependencies).

```bash
git clone https://github.com/aaronredzsir-star/when-your-antigravity-session-dies.git
cd when-your-antigravity-session-dies
```

*(Optional: run `pip install -e .` to use the global `agydoc` command)*

---

## 🛠️ Usage & Examples

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

### 2. Heal Bricked Sessions (`heal`)
Prunes oversized tool outputs, removes trailing retry errors, and unlocks sessions back to `IDLE`:

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
Every operation creates an automatic timestamped snapshot. Revert anytime:

```bash
python agydoc.py restore dd8201a0
```
```text
[+] Restored dd8201a0 from backup dd8201a0.db.bak_20261012_1145
```

---

## 📄 License

MIT
