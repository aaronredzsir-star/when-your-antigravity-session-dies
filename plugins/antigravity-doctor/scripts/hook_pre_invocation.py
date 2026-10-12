"""
Antigravity PreInvocation Hook for agydoc.
Safe guardian:
- NEVER truncates code, prompts, thoughts, or history.
- Only resets stuck status lock if the session was deadlocked.
- Injects 0 dummy steps.
"""

import sys
import json
import sqlite3
from pathlib import Path


def main():
    try:
        raw = sys.stdin.read()
        if not raw:
            print("{}")
            return
        data = json.loads(raw)
    except Exception:
        print("{}")
        return

    convo_id = data.get("conversationId")
    if not convo_id:
        print("{}")
        return

    home = Path.home()
    for gdir in [home / ".gemini" / "antigravity", home / ".gemini" / "antigravity-ide"]:
        db_file = gdir / "conversations" / f"{convo_id}.db"
        summ_db = gdir / "conversation_summaries.db"
        if db_file.exists() and summ_db.exists():
            try:
                conn = sqlite3.connect(str(db_file), timeout=1.0)
                max_idx = conn.execute("SELECT MAX(idx) FROM steps").fetchone()[0] or 0
                conn.close()

                s_conn = sqlite3.connect(str(summ_db), timeout=1.0)
                # Keep step_count strictly synced with max_idx + 1 so no historical steps are hidden in UI
                s_conn.execute("UPDATE conversation_summaries SET step_count = ? WHERE conversation_id = ? AND step_count < ?",
                               (max_idx + 1, convo_id, max_idx + 1))
                s_conn.commit()
                s_conn.close()
            except Exception:
                pass
            break

    print("{}")


if __name__ == "__main__":
    main()
