"""
Antigravity Stop Hook for agydoc.
Automatically handles connection interruptions or crash states upon turn termination.
Rewinds trailing aborted thoughts and error cascades back to the last valid completed step
and resets session status to IDLE so the session is never trapped in a retry/thought echo chamber.
"""

import sys
import json
import sqlite3
from pathlib import Path


def find_last_valid_step_idx(cur) -> int:
    rows = cur.execute("SELECT idx, step_type FROM steps ORDER BY idx DESC LIMIT 100").fetchall()
    if not rows:
        return 0
    has_error = any(stype == 17 for idx, stype in rows[:30])
    if not has_error:
        return rows[0][0]
    for idx, stype in rows:
        if stype in (17, 90, 15):
            continue
        else:
            return idx
    return rows[-1][0]


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

    # Only act if an error occurred or the loop stopped due to an error
    if not convo_id or (term_reason != "error" and not error_msg):
        print("{}")
        return

    home = Path.home()
    candidates = [
        (home / ".gemini" / "antigravity", home / ".gemini" / "antigravity" / "conversations" / f"{convo_id}.db"),
        (home / ".gemini" / "antigravity-ide", home / ".gemini" / "antigravity-ide" / "conversations" / f"{convo_id}.db"),
    ]

    for gdir, db_file in candidates:
        if db_file.exists():
            summ_db = gdir / "conversation_summaries.db"
            try:
                conn = sqlite3.connect(str(db_file), timeout=2.0)
                cur = conn.cursor()
                
                # Rewind trailing cascade
                last_valid = find_last_valid_step_idx(cur)
                cur_max = cur.execute("SELECT MAX(idx) FROM steps").fetchone()[0] or 0
                if cur_max > last_valid:
                    cur.execute("DELETE FROM steps WHERE idx > ?", (last_valid,))
                    conn.commit()
                conn.close()

                # Reset summary status to IDLE
                if summ_db.exists():
                    s_conn = sqlite3.connect(str(summ_db), timeout=2.0)
                    s_conn.execute("""
                        UPDATE conversation_summaries 
                        SET status = 'CASCADE_RUN_STATUS_IDLE', 
                            not_fully_idle = 0, 
                            step_count = ? 
                        WHERE conversation_id = ?
                    """, (last_valid + 1, convo_id))
                    s_conn.commit()
                    s_conn.close()
            except Exception:
                pass
            break

    print("{}")


if __name__ == "__main__":
    main()
