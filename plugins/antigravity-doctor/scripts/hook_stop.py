"""
Antigravity Stop Hook for agydoc.
Safe guardian:
- NEVER deletes user messages, assistant reasoning, or history.
- Cleans trailing broken retry loops (alternating 17/15) if session ended with an error.
- Resets status back to IDLE so the session never locks in RUNNING.
- Auto-compacts if post-checkpoint context bloat caused the drop (>200 KB).
"""

import sys
import os
import json
import sqlite3
from pathlib import Path

# Add plugin directory to sys.path so agy_doctor is self-contained
plugin_dir = Path(__file__).resolve().parent.parent
if str(plugin_dir) not in sys.path:
    sys.path.insert(0, str(plugin_dir))


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
                # 1. Clean trailing error steps and trailing incomplete retries
                conn = sqlite3.connect(str(db_file), timeout=2.0)
                cur = conn.cursor()
                deleted = 0
                while True:
                    last = cur.execute("SELECT idx, step_type FROM steps ORDER BY idx DESC LIMIT 1").fetchone()
                    if not last:
                        break
                    if last[1] == 17:
                        cur.execute("DELETE FROM steps WHERE idx = ?", (last[0],))
                        deleted += 1
                    elif last[1] == 15 and deleted > 0:
                        cur.execute("DELETE FROM steps WHERE idx = ?", (last[0],))
                        deleted += 1
                    else:
                        break
                conn.commit()

                # 2. Check if post-checkpoint bloat is severe (> 200 KB)
                last_ckp = cur.execute("SELECT MAX(idx) FROM steps WHERE step_type = 23").fetchone()
                last_ckp_idx = last_ckp[0] if (last_ckp and last_ckp[0] is not None) else 0
                post_ckp_bytes = cur.execute("SELECT COALESCE(SUM(LENGTH(step_payload)), 0) FROM steps WHERE idx > ?", (last_ckp_idx,)).fetchone()[0] or 0
                new_max = cur.execute("SELECT MAX(idx) FROM steps").fetchone()[0] or 0
                conn.close()

                if post_ckp_bytes > 200 * 1024:
                    try:
                        from agy_doctor.core import compact_session
                        session_info = {
                            "id": convo_id,
                            "title": "Auto-Compacted by agydoc",
                            "db_path": str(db_file),
                            "summ_db_path": str(summ_db)
                        }
                        compact_session(session_info, create_backup=False)
                    except Exception:
                        pass
                else:
                    if summ_db.exists():
                        s_conn = sqlite3.connect(str(summ_db), timeout=2.0)
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
