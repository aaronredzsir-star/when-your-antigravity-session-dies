"""
Antigravity PreInvocation Hook for agydoc.
Silently checks conversation database before LLM prefill:
1. Automatically rewinds any trailing aborted retry loops (stream interrupted errors & broken thoughts)
   so the model never gets trapped repeatedly thinking about the same failed step.
2. Silently deep-prunes historical tool outputs and redundant argument echoes in-place to prevent gateway timeouts.
3. NEVER injects dummy ephemeral messages into the conversation.
"""

import sys
import json
import sqlite3
from pathlib import Path


def decode_fields(b: bytes):
    i = 0
    fields = []
    n = len(b)
    while i < n:
        try:
            key = 0
            shift = 0
            while True:
                if i >= n:
                    break
                byte = b[i]
                i += 1
                key |= (byte & 0x7F) << shift
                if not (byte & 0x80):
                    break
                shift += 7
            fnum = key >> 3
            wtype = key & 7
            if wtype == 0:
                val = 0
                shift = 0
                while True:
                    if i >= n:
                        break
                    byte = b[i]
                    i += 1
                    val |= (byte & 0x7F) << shift
                    if not (byte & 0x80):
                        break
                    shift += 7
                fields.append((fnum, wtype, val))
            elif wtype == 2:
                length = 0
                shift = 0
                while True:
                    if i >= n:
                        break
                    byte = b[i]
                    i += 1
                    length |= (byte & 0x7F) << shift
                    if not (byte & 0x80):
                        break
                    shift += 7
                data = b[i:i+length]
                i += length
                fields.append((fnum, wtype, data))
            else:
                break
        except Exception:
            break
    return fields


def encode_varint(val: int) -> bytes:
    b = bytearray()
    while val > 0x7F:
        b.append((val & 0x7F) | 0x80)
        val >>= 7
    b.append(val & 0x7F)
    return bytes(b)


def encode_field(fnum: int, wtype: int, val) -> bytes:
    key = (fnum << 3) | wtype
    res = bytearray(encode_varint(key))
    if wtype == 0:
        res.extend(encode_varint(val))
    elif wtype == 2:
        res.extend(encode_varint(len(val)))
        res.extend(val)
    return bytes(res)


def truncate_text_slice(b: bytes, max_head: int = 300, max_tail: int = 100, marker_tag: str = "CodeContent") -> bytes:
    if len(b) <= max_head + max_tail + 50:
        return b
    head = b[:max_head]
    tail = b[-max_tail:]
    marker = f"\n... [{marker_tag} truncated by agydoc to preserve tokens] ...\n".encode("utf-8")
    return head + marker + tail


def prune_tool_payload(payload: bytes, max_output_chars: int = 400) -> bytes:
    fields = decode_fields(payload)
    if not fields:
        return payload

    stype_val = None
    for fnum, wtype, val in fields:
        if fnum == 1 and wtype == 0:
            stype_val = val
            break

    modified = False
    new_fields = bytearray()

    if stype_val == 132:
        for fnum, wtype, val in fields:
            if fnum == 5 and wtype == 2 and len(val) > 1500:
                sub = decode_fields(val)
                new_sub = bytearray()
                sub_mod = False
                for sfnum, sfwtype, sfval in sub:
                    if sfnum == 4 and sfwtype == 2 and len(sfval) > 1000:
                        trun = truncate_text_slice(sfval, max_head=350, max_tail=100, marker_tag="Historical Tool Args")
                        new_sub.extend(encode_field(sfnum, sfwtype, trun))
                        sub_mod = True
                    else:
                        new_sub.extend(encode_field(sfnum, sfwtype, sfval))
                if sub_mod:
                    new_fields.extend(encode_field(fnum, wtype, bytes(new_sub)))
                    modified = True
                else:
                    new_fields.extend(encode_field(fnum, wtype, val))

            elif fnum == 140 and wtype == 2 and len(val) > 1000:
                sub = decode_fields(val)
                new_sub = bytearray()
                sub_mod = False
                for sfnum, sfwtype, sfval in sub:
                    if sfnum == 1 and sfwtype == 2 and len(sfval) > 1000:
                        trun = truncate_text_slice(sfval, max_head=250, max_tail=80, marker_tag="CodeContent Arg")
                        new_sub.extend(encode_field(sfnum, sfwtype, trun))
                        sub_mod = True
                    elif sfnum == 2 and sfwtype == 2 and len(sfval) > max_output_chars:
                        trun = truncate_text_slice(sfval, max_head=max_output_chars, max_tail=120, marker_tag="Tool Output")
                        new_sub.extend(encode_field(sfnum, sfwtype, trun))
                        sub_mod = True
                    else:
                        new_sub.extend(encode_field(sfnum, sfwtype, sfval))
                if sub_mod:
                    new_fields.extend(encode_field(fnum, wtype, bytes(new_sub)))
                    modified = True
                else:
                    new_fields.extend(encode_field(fnum, wtype, val))
            else:
                new_fields.extend(encode_field(fnum, wtype, val))

    elif stype_val == 15:
        for fnum, wtype, val in fields:
            if fnum == 20 and wtype == 2 and len(val) > 2500:
                sub = decode_fields(val)
                new_sub = bytearray()
                sub_mod = False
                for sfnum, sfwtype, sfval in sub:
                    if sfnum == 7 and sfwtype == 2 and len(sfval) > 1500:
                        trun = truncate_text_slice(sfval, max_head=350, max_tail=100, marker_tag="Proposed CodeContent")
                        new_sub.extend(encode_field(sfnum, sfwtype, trun))
                        sub_mod = True
                    else:
                        new_sub.extend(encode_field(sfnum, sfwtype, sfval))
                if sub_mod:
                    new_fields.extend(encode_field(fnum, wtype, bytes(new_sub)))
                    modified = True
                else:
                    new_fields.extend(encode_field(fnum, wtype, val))
            else:
                new_fields.extend(encode_field(fnum, wtype, val))

    if modified:
        return bytes(new_fields)
    return payload


def find_last_valid_step_idx(cur) -> int:
    rows = cur.execute("SELECT idx, step_type FROM steps ORDER BY idx DESC LIMIT 100").fetchall()
    if not rows:
        return 0
    has_error = any(stype == 17 for idx, stype in rows[:30])
    is_dangling = (rows[0][1] == 15 and len(rows) > 1 and rows[1][1] not in (132, 101, 8))
    if not has_error and not is_dangling:
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
    if not convo_id:
        print("{}")
        return

    home = Path.home()
    candidates = [
        (home / ".gemini" / "antigravity", home / ".gemini" / "antigravity" / "conversations" / f"{convo_id}.db"),
        (home / ".gemini" / "antigravity-ide", home / ".gemini" / "antigravity-ide" / "conversations" / f"{convo_id}.db"),
    ]
    gdir, db_file = None, None
    for gd, dbf in candidates:
        if dbf.exists():
            gdir, db_file = gd, dbf
            break

    if not db_file:
        print("{}")
        return

    try:
        conn = sqlite3.connect(str(db_file), timeout=2.0)
        cur = conn.cursor()

        # 1. Rewind any trailing broken error cascade
        last_valid = find_last_valid_step_idx(cur)
        cur_max = cur.execute("SELECT MAX(idx) FROM steps").fetchone()[0] or 0
        if cur_max > last_valid:
            cur.execute("DELETE FROM steps WHERE idx > ?", (last_valid,))
            summ_db = gdir / "conversation_summaries.db"
            if summ_db.exists():
                s_conn = sqlite3.connect(str(summ_db), timeout=2.0)
                s_conn.execute("UPDATE conversation_summaries SET step_count = ?, status = 'CASCADE_RUN_STATUS_IDLE', not_fully_idle = 0 WHERE conversation_id = ?",
                               (last_valid + 1, convo_id))
                s_conn.commit()
                s_conn.close()

        # 2. Prune historical tool output and proposal bloat
        r_ckp = cur.execute("SELECT MAX(idx) FROM steps WHERE step_type = 23").fetchone()
        last_ckp = r_ckp[0] if (r_ckp and r_ckp[0] is not None) else 0

        rows = cur.execute(
            "SELECT idx, step_payload FROM steps WHERE idx > ? AND idx <= ? AND step_type IN (15, 132)",
            (last_ckp, last_valid)
        ).fetchall()

        for idx, payload in rows:
            if not payload or len(payload) < 1500:
                continue
            orig_len = len(payload)
            optimized = prune_tool_payload(payload, max_output_chars=400)
            if len(optimized) < orig_len:
                cur.execute("UPDATE steps SET step_payload = ? WHERE idx = ?", (optimized, idx))

        conn.commit()
        conn.close()
    except Exception:
        pass

    # Always return empty JSON object to avoid injecting dummy ephemeral steps
    print("{}")


if __name__ == "__main__":
    main()
