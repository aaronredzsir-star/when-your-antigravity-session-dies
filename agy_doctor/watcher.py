"""
Background watcher daemon for Antigravity Doctor.
Continuously monitors conversation databases and automatically heals bricked or bloated sessions.
"""

import time
import datetime
import logging
from pathlib import Path
from typing import Optional

from .core import scan_sessions, heal_session

logger = logging.getLogger("agydoc.watcher")


def run_watch_loop(interval_sec: int = 15, bloat_threshold_kb: int = 350, max_idle_sec: int = 45):
    """
    Main watch loop:
    1. Checks all sessions every `interval_sec` seconds.
    2. If a session is BRICKED (hanging in error loop or stuck in RUNNING lock), auto-heals it.
    3. If a session exceeds `bloat_threshold_kb`, auto-prunes its tool payloads in-place.
    """
    print(f"[*] Antigravity Doctor Watcher started.")
    print(f"[*] Check interval: {interval_sec}s | Bloat trigger: >{bloat_threshold_kb} KB | Stuck timeout: >{max_idle_sec}s")
    print(f"[*] Press Ctrl+C to stop.\n")

    while True:
        try:
            sessions = scan_sessions()
            for s in sessions:
                now = datetime.datetime.now()
                db_path = Path(s["db_path"])
                mtime = datetime.datetime.fromtimestamp(db_path.stat().st_mtime)
                elapsed_sec = (now - mtime).total_seconds()

                should_heal = False
                heal_reason = ""

                # Condition 1: Bricked session (hanging errors or deadlocked RUNNING status that has gone silent)
                if s["health"] == "BRICKED":
                    # If it has active error steps at tail, it's stuck in retry loop
                    if "Hanging in EOF / dropped connection error loop" in s.get("reasons", []):
                        should_heal = True
                        heal_reason = "Trailing EOF / retry loop detected"
                    elif s["status"] == "CASCADE_RUN_STATUS_RUNNING" and elapsed_sec > max_idle_sec:
                        should_heal = True
                        heal_reason = f"Stuck in RUNNING lock without activity for {int(elapsed_sec)}s"

                # Condition 2: Severe context bloat
                elif s["bloat_bytes"] > (bloat_threshold_kb * 1024):
                    # Only prune if session is IDLE to prevent competing with active streaming turns
                    if s["status"] != "CASCADE_RUN_STATUS_RUNNING" or elapsed_sec > max_idle_sec:
                        should_heal = True
                        heal_reason = f"Context bloat exceeded threshold ({s['bloat_bytes'] / 1024:.0f} KB)"

                if should_heal:
                    timestamp_str = datetime.datetime.now().strftime("%H:%M:%S")
                    print(f"[{timestamp_str}] [!] Auto-healing session {s['id'][:8]} ({s['title']})...")
                    print(f"           Reason: {heal_reason}")
                    try:
                        res = heal_session(s)
                        print(f"           -> Rescued! Pruned {res['pruned_steps']} steps (-{res['saved_kb']:.1f} KB), "
                              f"removed {res['deleted_error_steps']} errors. State is now IDLE.\n")
                    except Exception as e:
                        print(f"           -> Healing failed: {e}\n")

            time.sleep(interval_sec)
        except KeyboardInterrupt:
            print("\n[*] Watcher stopped.")
            break
        except Exception as e:
            time.sleep(interval_sec)
