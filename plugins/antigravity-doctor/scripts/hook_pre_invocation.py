"""
Antigravity PreInvocation Hook for agydoc.
Automatically checks conversation database before LLM prefill.
If historical tool outputs exceed the bloat threshold, silently prunes them in-place
to prevent gateway timeouts and 10-minute retry deadlocks.
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


def prune_tool_payload(payload: bytes, max_output_chars: int = 500) -> bytes:
    fields = decode_fields(payload)
    has_large_f140 = False
    new_f140_bytes = None
    for fnum, wtype, val in fields:
        if fnum == 140 and wtype == 2 and len(val) > 1000:
            subfields = decode_fields(val)
            new_subfields = bytearray()
            for sf_num, sf_wtype, sf_val in subfields:
                if sf_num == 2 and sf_wtype == 2 and len(sf_val) > max_output_chars:
                    has_large_f140 = True
                    head = sf_val[:max_output_chars]
                    tail = sf_val[-150:]
                    marker = b"\n... [Output pruned by agydoc-plugin for context optimization] ...\n"
                    truncated = head + marker + tail
                    new_subfields.extend(encode_field(sf_num, sf_wtype, truncated))
                else:
                    new_subfields.extend(encode_field(sf_num, sf_wtype, sf_val))
            new_f140_bytes = bytes(new_subfields)
    if has_large_f140 and new_f140_bytes:
        new_payload = bytearray()
        for fnum, wtype, val in fields:
            if fnum == 140:
                new_payload.extend(encode_field(fnum, wtype, new_f140_bytes))
            else:
                new_payload.extend(encode_field(fnum, wtype, val))
        return bytes(new_payload)
    return payload


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
        home / ".gemini" / "antigravity" / "conversations" / f"{convo_id}.db",
        home / ".gemini" / "antigravity-ide" / "conversations" / f"{convo_id}.db",
    ]
    db_file = None
    for c in candidates:
        if c.exists():
            db_file = c
            break

    if not db_file:
        print("{}")
        return

    pruned_count = 0
    saved_bytes = 0
    try:
        conn = sqlite3.connect(str(db_file), timeout=2.0)
        cur = conn.cursor()
        r_ckp = cur.execute("SELECT MAX(idx) FROM steps WHERE step_type = 23").fetchone()
        last_ckp = r_ckp[0] if (r_ckp and r_ckp[0] is not None) else 0

        rows = cur.execute(
            "SELECT idx, step_payload FROM steps WHERE idx > ? AND step_type = 132 AND length(step_payload) > 2000",
            (last_ckp,)
        ).fetchall()

        # Only trigger if total bloated steps >= 5 or total bloat > 150KB
        total_len = sum(len(r[1]) for r in rows if r[1])
        if total_len > 150 * 1024 or len(rows) >= 8:
            for idx, payload in rows:
                if not payload:
                    continue
                orig_len = len(payload)
                optimized = prune_tool_payload(payload, max_output_chars=500)
                if len(optimized) < orig_len:
                    cur.execute("UPDATE steps SET step_payload = ? WHERE idx = ?", (optimized, idx))
                    pruned_count += 1
                    saved_bytes += (orig_len - len(optimized))

            if pruned_count > 0:
                conn.commit()

        conn.close()
    except Exception:
        pass

    if pruned_count > 0:
        res = {
            "injectSteps": [
                {
                    "ephemeralMessage": f"[agydoc-plugin] Auto-pruned {pruned_count} historical tool dumps (-{saved_bytes/1024:.0f} KB) to keep prefill fast."
                }
            ]
        }
        print(json.dumps(res))
    else:
        print("{}")


if __name__ == "__main__":
    main()
