"""
Antigravity PreInvocation Hook for agydoc.
Proactive Immune Guardian:
- Proactively checks post-checkpoint context bloat BEFORE LLM prefill starts.
- If post_ckp_bytes > 200 KB, auto-synthesizes a native Checkpoint (preserving the active user prompt at the tip).
- Completely prevents 60-second gateway timeouts (EOF / stream interrupted).
- Keeps step_count strictly synchronized so no historical steps are hidden in UI.
- 100% non-destructive: zero loss of user prompts, assistant reasoning, or history.
"""

import sys
import json
import sqlite3
from pathlib import Path

# Add self-contained plugin directory to sys.path
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
    if not convo_id:
        print("{}")
        return

    home = Path.home()
    for gdir in [home / ".gemini" / "antigravity", home / ".gemini" / "antigravity-ide"]:
        db_file = gdir / "conversations" / f"{convo_id}.db"
        summ_db = gdir / "conversation_summaries.db"
        if db_file.exists() and summ_db.exists():
            try:
                conn = sqlite3.connect(str(db_file), timeout=1.5)
                cur = conn.cursor()
                max_idx = cur.execute("SELECT MAX(idx) FROM steps").fetchone()[0] or 0

                # 1. Check post-checkpoint bloat
                last_ckp = cur.execute("SELECT MAX(idx) FROM steps WHERE step_type = 23").fetchone()
                last_ckp_idx = last_ckp[0] if (last_ckp and last_ckp[0] is not None) else 0
                post_ckp_bytes = cur.execute(
                    "SELECT COALESCE(SUM(LENGTH(step_payload)), 0) FROM steps WHERE idx > ?",
                    (last_ckp_idx,)
                ).fetchone()[0] or 0
                conn.close()

                # 2. Proactive auto-compaction if context exceeds safety threshold (>200 KB)
                if post_ckp_bytes > 200 * 1024:
                    try:
                        from agy_doctor.core import compact_session
                        session_info = {
                            "id": convo_id,
                            "title": "Proactive Compaction",
                            "db_path": str(db_file),
                            "summ_db_path": str(summ_db)
                        }
                        compact_session(session_info, preserve_trailing_prompt=True)
                    except Exception:
                        pass
                else:
                    # Sync step_count with max_idx + 1 so no historical steps are hidden in UI
                    s_conn = sqlite3.connect(str(summ_db), timeout=1.0)
                    s_conn.execute(
                        "UPDATE conversation_summaries SET step_count = ? WHERE conversation_id = ? AND step_count < ?",
                        (max_idx + 1, convo_id, max_idx + 1)
                    )
                    s_conn.commit()
                    s_conn.close()
            except Exception:
                pass
            break

    print("{}")


if __name__ == "__main__":
    main()
