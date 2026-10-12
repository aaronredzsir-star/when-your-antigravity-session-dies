"""
Antigravity Stop Hook for agydoc.
Safe guardian:
- NEVER deletes user messages, assistant reasoning, or history.
- Only rolls back the single trailing interrupted error step (step_type == 17) if the session ended with an error.
- Resets status back to IDLE so the session never locks in RUNNING.
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
    term_reason = data.get("terminationReason", "")
    error_msg = data.get("error", "")

    if not convo_id or (term_reason != "error" and not error_msg):
        print("{}")
        return

    home = Path.home()
    for gdir in [home / ".gemini" / "antigravity", home / ".gemini" / "antigravity-ide"]:
        db_file = gdir / "conversations" / f"{convo_id}.db"
        summ_db = gdir / "conversation_summaries.db"
        if db_file.exists():
            try:
                conn = sqlite3.connect(str(db_file), timeout=1.5)
                cur = conn.cursor()
                # Only remove trailing step 17 if at the very tip
                while True:
                    last = cur.execute("SELECT idx, step_type FROM steps ORDER BY idx DESC LIMIT 1").fetchone()
                    if not last or last[1] != 17:
                        break
                    cur.execute("DELETE FROM steps WHERE idx = ?", (last[0],))
                new_max = cur.execute("SELECT MAX(idx) FROM steps").fetchone()[0] or 0
                conn.commit()
                conn.close()

                if summ_db.exists():
                    s_conn = sqlite3.connect(str(summ_db), timeout=1.5)
                    s_conn.execute("""
                        UPDATE conversation_summaries 
                        SET status = 'CASCADE_RUN_STATUS_IDLE', 
                            not_fully_idle = 0, 
                            step_count = ? 
                        WHERE conversation_id = ?
                    """, (new_max + 1, convo_id))
                    s_conn.commit()
                    s_conn.close()
            except Exception:
                pass
            break

    print("{}")


if __name__ == "__main__":
    main()
