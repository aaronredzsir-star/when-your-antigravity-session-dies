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

from .proto_utils import prune_tool_payload


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
            
            try:
                c_conn = sqlite3.connect(db_file)
                r_max = c_conn.execute("SELECT MAX(idx), COUNT(*) FROM steps").fetchone()
                if r_max and r_max[0] is not None:
                    max_idx = r_max[0]
                    total_steps = r_max[1]
                    
                r_ckp = c_conn.execute("SELECT MAX(idx) FROM steps WHERE step_type = 23").fetchone()
                if r_ckp and r_ckp[0] is not None:
                    last_checkpoint_idx = r_ckp[0]
                    
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
            elif size_mb > 25:
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
                "bloat_bytes": 0,
                "health": health,
                "reasons": reasons,
                "status": meta["status"]
            })
            
    sessions.sort(key=lambda s: s["size_mb"], reverse=True)
    return sessions


def heal_session(session_info: Dict, dry_run: bool = False) -> Dict:
    """
    Safely heals a bloated or bricked session with ZERO destruction:
    1. Creates timestamped safety backups of conversation DB and summaries DB.
    2. Removes ONLY trailing error steps (step_type == 17) at the very tip if blocking.
    3. Resets conversation summary status to IDLE and sets step_count = MAX(idx) + 1 so ALL steps show in UI.
    4. Validates database integrity.
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
    
    # 1. Only remove trailing step 17 error steps at the very tip
    deleted_error_steps = 0
    if not dry_run:
        while True:
            last = cur.execute("SELECT idx, step_type FROM steps ORDER BY idx DESC LIMIT 1").fetchone()
            if not last or last[1] != 17:
                break
            cur.execute("DELETE FROM steps WHERE idx = ?", (last[0],))
            deleted_error_steps += 1
            
    new_max = cur.execute("SELECT MAX(idx) FROM steps").fetchone()[0] or 0
    if not dry_run:
        conn.commit()
        integrity = cur.execute("PRAGMA integrity_check").fetchone()[0]
    else:
        integrity = "ok (dry-run)"
        
    conn.close()
    
    # 2. Reset summary status to IDLE and ensure step_count matches full max_idx + 1
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
        
    return {
        "id": session_info["id"],
        "title": session_info["title"],
        "backup_path": str(conv_bak) if not dry_run else "dry-run",
        "deleted_error_steps": deleted_error_steps,
        "cleaned_noise_steps": 0,
        "pruned_steps": 0,
        "saved_kb": 0.0,
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
