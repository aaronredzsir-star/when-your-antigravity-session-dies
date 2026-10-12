---
name: agydoc
description: >-
  Inspect Antigravity session health, evaluate context bloat, and rescue deadlocked
  or bloated conversation sessions using Antigravity Doctor.
---

# Antigravity Doctor (`agydoc`) Skill

Use this skill when:
- An Antigravity session is becoming sluggish, approaching context window limits, or experiencing gateway timeout retries.
- You need to scan local session health across Antigravity and Antigravity IDE.
- You need to prune historical tool dumps to restore fast model prefills.

## Common Operations

### 1. Scan Sessions
```bash
python agydoc.py scan
```
Shows active and historical sessions, their file size, step count, and health status (`HEALTHY`, `WARNING`, or `BRICKED`).

### 2. Auto-Heal Bloated or Bricked Sessions
```bash
# Heal all bloated or bricked sessions
python agydoc.py heal --all

# Or heal a specific conversation
python agydoc.py heal <session-id>
```

### 3. Continuous Background Monitoring
```bash
python agydoc.py watch
```
Monitors conversation databases and automatically resolves any stuck loops or payload bloat without user intervention.
