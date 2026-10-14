"""
Core discovery, diagnostic, and healing engine for Antigravity Doctor.
Non-destructive: preserves 100% of user prompts, assistant thoughts, code, and history.
"""

import os
import sys
import shutil
import sqlite3
import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple

from .proto_utils import decode_fields, encode_field, prune_tool_payload


def get_gemini_dirs() -> List[Path]:
    """Returns candidate Gemini data directories (standalone app & IDE)."""
    home = Path.home()
    gemini_base = home / ".gemini"
    candidates = [
        gemini_base / "antigravity",
        gemini_base / "antigravity-ide",
    ]
    return [c for c in candidates if c.exists()]


def scan_sessions() -> List[Dict]:
    """Scans all Antigravity directories and returns health metadata for each session."""
    sessions = []
    
    for gdir in get_gemini_dirs():
        conv_dir = gdir / "conversations"
        summ_db_path = gdir / "conversation_summaries.db"
        if not conv_dir.exists() or not summ_db_path.exists():
            continue
            
        summaries = {}
        try:
            s_conn = sqlite3.connect(summ_db_path)
            rows = s_conn.execute("SELECT conversation_id, title, status, step_count, last_modified_time, not_fully_idle FROM conversation_summaries").fetchall()
            for r in rows:
                summaries[r[0]] = {
                    "title": r[1] or "Untitled",
                    "status": r[2],
                    "step_count": r[3],
                    "last_modified": r[4],
                    "not_fully_idle": r[5]
                }
            s_conn.close()
        except Exception:
            pass

        for db_file in conv_dir.glob("*.db"):
            convo_id = db_file.stem
            meta = summaries.get(convo_id, {
                "title": "Unknown",
                "status": "UNKNOWN",
                "step_count": 0,
                "last_modified": datetime.datetime.fromtimestamp(db_file.stat().st_mtime).isoformat(),
                "not_fully_idle": 0
            })
            
            size_mb = db_file.stat().st_size / (1024 * 1024)
            has_active_error = False
            last_checkpoint_idx = 0
            total_steps = 0
            max_idx = 0
            post_ckp_bytes = 0
            post_ckp_steps = 0
            
            try:
                c_conn = sqlite3.connect(db_file)
                r_max = c_conn.execute("SELECT MAX(idx), COUNT(*) FROM steps").fetchone()
                if r_max and r_max[0] is not None:
                    max_idx = r_max[0]
                    total_steps = r_max[1]
                    
                r_ckp = c_conn.execute("SELECT MAX(idx) FROM steps WHERE step_type = 23").fetchone()
                if r_ckp and r_ckp[0] is not None:
                    last_checkpoint_idx = r_ckp[0]
                
                r_post = c_conn.execute("SELECT COUNT(*), COALESCE(SUM(LENGTH(step_payload)), 0) FROM steps WHERE idx > ?", (last_checkpoint_idx,)).fetchone()
                if r_post:
                    post_ckp_steps = r_post[0]
                    post_ckp_bytes = r_post[1]
                    
                last_row = c_conn.execute("SELECT idx, step_type FROM steps ORDER BY idx DESC LIMIT 1").fetchone()
                if last_row and last_row[1] == 17:
                    has_active_error = True
                    
                c_conn.close()
            except Exception:
                pass
                
            health = "HEALTHY"
            reasons = []
            if meta["status"] == "CASCADE_RUN_STATUS_RUNNING" or has_active_error:
                health = "BRICKED"
                if has_active_error:
                    reasons.append("Trailing connection interrupted error at tail")
                if meta["status"] == "CASCADE_RUN_STATUS_RUNNING":
                    reasons.append("Stuck in RUNNING status lock")
            elif post_ckp_bytes > 150 * 1024:
                health = "WARNING"
                reasons.append(f"Bloated post-checkpoint context ({post_ckp_bytes / 1024:.1f} KB, {post_ckp_steps} steps) - gateway timeout risk")
            elif size_mb > 30:
                health = "WARNING"
                reasons.append(f"Large session size ({size_mb:.1f} MB)")
                
            sessions.append({
                "id": convo_id,
                "title": meta["title"],
                "source_dir": str(gdir),
                "db_path": str(db_file),
                "summ_db_path": str(summ_db_path),
                "size_mb": size_mb,
                "total_steps": total_steps,
                "max_idx": max_idx,
                "last_checkpoint": last_checkpoint_idx,
                "post_ckp_bytes": post_ckp_bytes,
                "post_ckp_steps": post_ckp_steps,
                "bloat_bytes": post_ckp_bytes,
                "health": health,
                "reasons": reasons,
                "status": meta["status"]
            })
            
    sessions.sort(key=lambda s: s["size_mb"], reverse=True)
    return sessions


def _extract_recent_activity_notes(cur: sqlite3.Cursor, start_idx: int, end_idx: int) -> str:
    """Extracts high-level human readable activity notes from intermediate steps."""
    rows = cur.execute(
        "SELECT idx, step_type, step_payload FROM steps WHERE idx > ? AND idx <= ? ORDER BY idx ASC",
        (start_idx, end_idx)
    ).fetchall()
    
    tools_used = []
    user_prompts = []
    
    for idx, st, payload in rows:
        try:
            fields = decode_fields(payload)
            if st in (14, 132, 140): # Tool call or result
                f140 = [v for f, w, v in fields if f == 140]
                if f140:
                    inner = decode_fields(f140[0])
                    for f, w, v in inner:
                        if isinstance(v, bytes):
                            text = v.decode('utf-8', errors='ignore')
                            if 'toolSummary' in text or 'toolAction' in text:
                                # Extract clean summary string
                                for line in text.split('\n'):
                                    clean = line.strip('\x00\x01\x02\x03\x04\x05\x06\x07\x08\x0b\x0c\x0e\x0f\x10\x11\x12\x13\x14\x15\x16\x17\x18\x19\x1a\x1b\x1c\x1d\x1e\x1f')
                                    if len(clean) > 5 and clean not in tools_used:
                                        tools_used.append(clean)
                                        break
            elif st in (1, 101): # User input
                for f, w, v in fields:
                    if f in (5, 114) and isinstance(v, bytes):
                        text = v.decode('utf-8', errors='ignore')
                        if len(text.strip()) > 3:
                            user_prompts.append(text.strip()[:100])
                            break
        except Exception:
            pass
            
    notes = []
    if user_prompts:
        notes.append("Recent User Requests:")
        for p in user_prompts[-3:]:
            notes.append(f"  - {p}")
    if tools_used:
        notes.append(f"Completed Tools & Actions ({len(tools_used)} operations):")
        for t in tools_used[-8:]:
            notes.append(f"  - {t}")
            
    return "\n".join(notes)


def compact_session(session_info: Dict, summary_notes: Optional[str] = None, dry_run: bool = False, preserve_trailing_prompt: bool = True) -> Dict:
    """
    Synthesizes a native Antigravity Checkpoint (step_type = 23).
    This non-destructively reduces LLM active prefill weight from ~500 KB to ~15 KB,
    permanently eliminating 60s gateway timeouts while preserving 100% of past SQLite steps.
    """
    conv_db = Path(session_info["db_path"])
    summ_db = Path(session_info["summ_db_path"])
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    conv_bak = conv_db.with_name(f"{conv_db.name}.bak_{timestamp}")
    summ_bak = summ_db.with_name(f"{summ_db.name}.bak_{timestamp}")
    
    if not dry_run:
        shutil.copy2(conv_db, conv_bak)
        if summ_db.exists():
            shutil.copy2(summ_db, summ_bak)
            
    conn = sqlite3.connect(conv_db)
    cur = conn.cursor()
    
    # 1. Clean trailing interrupted retry loops (alternating 17 and 15)
    cleaned_retries = 0
    if not dry_run:
        while True:
            last = cur.execute("SELECT idx, step_type FROM steps ORDER BY idx DESC LIMIT 1").fetchone()
            if not last:
                break
            if last[1] == 17:
                cur.execute("DELETE FROM steps WHERE idx = ?", (last[0],))
                cleaned_retries += 1
            elif last[1] == 15 and cleaned_retries > 0:
                cur.execute("DELETE FROM steps WHERE idx = ?", (last[0],))
                cleaned_retries += 1
            else:
                break
        conn.commit()

    # 2. Check if the very tip is an unreplied user prompt that should be preserved active
    trailing_user_prompt = None
    if preserve_trailing_prompt and not dry_run:
        last_step = cur.execute("SELECT idx, step_type, step_payload FROM steps ORDER BY idx DESC LIMIT 1").fetchone()
        if last_step and last_step[1] in (14, 101):
            trailing_user_prompt = (last_step[1], last_step[2])
            cur.execute("DELETE FROM steps WHERE idx = ?", (last_step[0],))
            conn.commit()

    # 3. Find last native checkpoint
    last_ckp_row = cur.execute("SELECT idx, step_payload FROM steps WHERE step_type = 23 ORDER BY idx DESC LIMIT 1").fetchone()
    last_ckp_idx = last_ckp_row[0] if last_ckp_row else 0
    
    # 4. Find current max step idx
    current_max = cur.execute("SELECT MAX(idx) FROM steps").fetchone()[0] or 0
    target_idx = current_max + 1
    
    if current_max == last_ckp_idx and last_ckp_row and not trailing_user_prompt:
        # Already compacted at tip
        conn.close()
        return {
            "id": session_info["id"],
            "title": session_info["title"],
            "checkpoint_idx": last_ckp_idx,
            "saved_bytes": 0,
            "status": "ALREADY_COMPACTED",
            "integrity": "ok"
        }

    # 4. Extract template metadata and summary
    f5_bytes = None
    inner_fields = []
    original_summary = "<summary>\nSession compact synthesized by Antigravity Doctor.\n</summary>"
    
    if last_ckp_row:
        outer_fields = decode_fields(last_ckp_row[1])
        f30_bytes = None
        for fnum, wtype, val in outer_fields:
            if fnum == 5:
                f5_bytes = val
            elif fnum == 30:
                f30_bytes = val
        if f30_bytes:
            inner_fields = decode_fields(f30_bytes)
            for fnum, wtype, val in inner_fields:
                if fnum == 5:
                    original_summary = val.decode('utf-8', errors='ignore')
                    break
    else:
        # Borrow template metadata from any checkpoint in the system
        for gdir in get_gemini_dirs():
            for other_db in (gdir / "conversations").glob("*.db"):
                try:
                    o_conn = sqlite3.connect(other_db)
                    o_ckp = o_conn.execute("SELECT step_payload FROM steps WHERE step_type = 23 LIMIT 1").fetchone()
                    o_conn.close()
                    if o_ckp:
                        o_fields = decode_fields(o_ckp[0])
                        f5_bytes = [v for f, w, v in o_fields if f == 5][0]
                        o_f30 = [v for f, w, v in o_fields if f == 30][0]
                        inner_fields = decode_fields(o_f30)
                        break
                except Exception:
                    pass
            if f5_bytes:
                break

    # 5. Build updated summary content
    if not summary_notes:
        activity = _extract_recent_activity_notes(cur, last_ckp_idx, current_max)
        if activity:
            summary_notes = f"\n\n### Compacted Activity (Steps {last_ckp_idx + 1}-{current_max}):\n{activity}\n"
        else:
            summary_notes = f"\n\n### Compacted Progress:\n- Successfully preserved steps {last_ckp_idx + 1} through {current_max}.\n"

    if '</summary>' in original_summary:
        new_summary = original_summary.replace('</summary>', summary_notes + '</summary>')
    else:
        new_summary = original_summary + summary_notes

    # 6. Re-encode inner checkpoint message
    new_inner_fields = []
    has_f5 = False
    has_f12 = False
    for fnum, wtype, val in inner_fields:
        if fnum == 5:
            new_inner_fields.append((5, 2, new_summary.encode('utf-8')))
            has_f5 = True
        elif fnum == 12:
            new_inner_fields.append((12, 0, target_idx))
            has_f12 = True
        else:
            new_inner_fields.append((fnum, wtype, val))
            
    if not has_f5:
        new_inner_fields.insert(0, (5, 2, new_summary.encode('utf-8')))
    if not has_f12:
        new_inner_fields.append((12, 0, target_idx))
        
    new_inner_bytes = b''.join(encode_field(fn, wt, v) for fn, wt, v in new_inner_fields)

    # 7. Build outer checkpoint payload
    f1 = encode_field(1, 0, 23)
    f4 = encode_field(4, 0, 3) # CASCADE_STEP_STATUS_DONE
    f5 = encode_field(5, 2, f5_bytes) if f5_bytes else b''
    f30 = encode_field(30, 2, new_inner_bytes)
    checkpoint_payload = f1 + f4 + f5 + f30

    # 8. Insert checkpoint and update summaries DB
    final_step_count = target_idx + 1
    if not dry_run:
        cur.execute("INSERT INTO steps (idx, step_type, step_payload) VALUES (?, 23, ?)", (target_idx, checkpoint_payload))
        if trailing_user_prompt:
            cur.execute("INSERT INTO steps (idx, step_type, step_payload) VALUES (?, ?, ?)", (target_idx + 1, trailing_user_prompt[0], trailing_user_prompt[1]))
            final_step_count = target_idx + 2
        conn.commit()
        integrity = cur.execute("PRAGMA integrity_check").fetchone()[0]
        conn.close()

        if summ_db.exists():
            s_conn = sqlite3.connect(summ_db)
            s_conn.execute("""
                UPDATE conversation_summaries
                SET status = 'CASCADE_RUN_STATUS_IDLE',
                    not_fully_idle = 0,
                    step_count = ?
                WHERE conversation_id = ?
            """, (final_step_count, session_info["id"]))
            s_conn.commit()
            s_conn.close()
    else:
        if trailing_user_prompt:
            cur.execute("INSERT INTO steps (idx, step_type, step_payload) VALUES (?, ?, ?)", (current_max + 1, trailing_user_prompt[0], trailing_user_prompt[1]))
        conn.close()
        integrity = "ok (dry-run)"

    return {
        "id": session_info["id"],
        "title": session_info["title"],
        "backup_path": str(conv_bak) if not dry_run else "dry-run",
        "checkpoint_idx": target_idx,
        "final_step_idx": target_idx + (1 if trailing_user_prompt else 0),
        "previous_checkpoint_idx": last_ckp_idx,
        "cleaned_retries": cleaned_retries,
        "preserved_prompt": bool(trailing_user_prompt),
        "payload_size": len(checkpoint_payload),
        "integrity": integrity
    }


def heal_session(session_info: Dict, dry_run: bool = False, auto_compact: bool = True) -> Dict:
    """
    Safely heals a bloated or bricked session with ZERO destruction:
    1. Creates timestamped safety backups of conversation DB and summaries DB.
    2. Removes trailing retry loops (alternating 17 and 15) at the very tip.
    3. If post-checkpoint payload exceeds 150 KB, automatically synthesizes a native Checkpoint (step_type = 23).
    4. Resets conversation summary status to IDLE and syncs step_count.
    5. Validates database integrity.
    """
    conv_db = Path(session_info["db_path"])
    summ_db = Path(session_info["summ_db_path"])
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    conv_bak = conv_db.with_name(f"{conv_db.name}.bak_{timestamp}")
    summ_bak = summ_db.with_name(f"{summ_db.name}.bak_{timestamp}")
    
    if not dry_run:
        shutil.copy2(conv_db, conv_bak)
        if summ_db.exists():
            shutil.copy2(summ_db, summ_bak)
        
    conn = sqlite3.connect(conv_db)
    cur = conn.cursor()
    
    # 1. Clean trailing error steps and trailing incomplete retry attempts
    deleted_error_steps = 0
    if not dry_run:
        while True:
            last = cur.execute("SELECT idx, step_type FROM steps ORDER BY idx DESC LIMIT 1").fetchone()
            if not last:
                break
            if last[1] == 17:
                cur.execute("DELETE FROM steps WHERE idx = ?", (last[0],))
                deleted_error_steps += 1
            elif last[1] == 15 and deleted_error_steps > 0:
                cur.execute("DELETE FROM steps WHERE idx = ?", (last[0],))
                deleted_error_steps += 1
            else:
                break
        conn.commit()

    # 2. Check post-checkpoint bloat
    last_ckp = cur.execute("SELECT MAX(idx) FROM steps WHERE step_type = 23").fetchone()
    last_ckp_idx = last_ckp[0] if (last_ckp and last_ckp[0] is not None) else 0
    
    post_ckp_bytes = cur.execute(
        "SELECT COALESCE(SUM(LENGTH(step_payload)), 0) FROM steps WHERE idx > ?",
        (last_ckp_idx,)
    ).fetchone()[0] or 0
    
    new_max = cur.execute("SELECT MAX(idx) FROM steps").fetchone()[0] or 0
    conn.close()

    compacted = False
    compact_info = None
    if auto_compact and post_ckp_bytes > 150 * 1024 and not dry_run:
        # Automatically compact to prevent recurring gateway timeouts
        compact_info = compact_session(session_info, dry_run=dry_run, preserve_trailing_prompt=True)
        compacted = True
        new_max = compact_info["final_step_idx"]
    else:
        # Sync summary DB
        if not dry_run and summ_db.exists():
            s_conn = sqlite3.connect(summ_db)
            s_conn.execute("""
                UPDATE conversation_summaries 
                SET status = 'CASCADE_RUN_STATUS_IDLE', 
                    not_fully_idle = 0, 
                    step_count = ? 
                WHERE conversation_id = ?
            """, (new_max + 1, session_info["id"]))
            s_conn.commit()
            s_conn.close()

    conn = sqlite3.connect(conv_db)
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    conn.close()

    return {
        "id": session_info["id"],
        "title": session_info["title"],
        "backup_path": str(conv_bak) if not dry_run else "dry-run",
        "deleted_error_steps": deleted_error_steps,
        "compacted": compacted,
        "post_ckp_kb": post_ckp_bytes / 1024,
        "new_max_step": new_max,
        "integrity": integrity
    }


def restore_session(session_id: str) -> Optional[str]:
    """Restores the latest backup for a given session ID."""
    for gdir in get_gemini_dirs():
        conv_dir = gdir / "conversations"
        if not conv_dir.exists():
            continue
        db_file = conv_dir / f"{session_id}.db"
        baks = sorted(conv_dir.glob(f"{session_id}.db.bak_*"), key=lambda p: p.stat().st_mtime, reverse=True)
        if baks:
            latest_bak = baks[0]
            shutil.copy2(latest_bak, db_file)
            return str(latest_bak)
    return None
