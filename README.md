# 🩺 Antigravity Doctor (`agydoc`)

> Fix bricked sessions and the 10-minute retry loop in Google Antigravity. Zero dependencies.

---

## The Problem

When Antigravity sessions grow long, accumulated tool outputs (`view_file`, terminal dumps) bloat the local SQLite database. Once the server prompt cache expires, the next prefill takes >50s with zero keep-alive bytes streamed—triggering an API gateway timeout (`The stream was interrupted`).

Because Antigravity's auto-compaction only runs after a *successful* turn, crashing mid-flight traps the session in a 10-minute retry hell with no manual way to recover.

## What `agydoc` Does

`agydoc` performs non-destructive, in-place protobuf surgery on your local database (`~/.gemini/antigravity`):

* ✂️ **Prunes bloated tool dumps**: Truncates repetitive historical tool outputs while preserving 100% of user prompts, assistant thoughts, and diffs.
* 🔓 **Unlocks deadlocks**: Clears dangling retry errors and resets sessions back to `IDLE`.
* 🛡️ **Zero risk**: Automatically creates a timestamped `.bak` snapshot before any modification, with instant `restore`.

---

## ⚡ Quickstart

Requires Python 3.8+ (no external packages needed).

```bash
git clone https://github.com/aaronredzsir-star/when-your-antigravity-session-dies.git
cd when-your-antigravity-session-dies

# 1. Scan session health
python agydoc.py scan

# 2. Heal bricked or bloated sessions
python agydoc.py heal --all

# 3. (Optional) Roll back if needed
python agydoc.py restore <session-id>
```

Or install as a global CLI:
```bash
pip install -e .
agydoc heal --all
```

---

## 📄 License

MIT
