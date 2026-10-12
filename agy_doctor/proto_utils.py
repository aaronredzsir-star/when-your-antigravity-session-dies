"""
Protobuf wire-format parser and deep re-encoder without external dependencies.
Safely prunes oversized historical tool payloads and redundant CodeContent across:
  - Step 132 Field 140 (Tool input args & tool output bodies)
  - Step 132 Field 5 (Tool call execution records)
  - Step 15 Field 20 (Historical tool call proposals with massive embedded code)
Preserves 100% of user prompts, assistant thoughts, tool metadata, and file paths.
"""

def decode_fields(b: bytes):
    """
    Decodes raw protobuf wire-format bytes into a list of (field_num, wire_type, value).
    Handles:
      - wire_type 0: varint
      - wire_type 2: length-delimited bytes
    """
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
            
            if wtype == 0:  # varint
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
            elif wtype == 2:  # length-delimited
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
    """Encodes an integer into protobuf varint format."""
    b = bytearray()
    while val > 0x7F:
        b.append((val & 0x7F) | 0x80)
        val >>= 7
    b.append(val & 0x7F)
    return bytes(b)


def encode_field(fnum: int, wtype: int, val) -> bytes:
    """Encodes a single protobuf field into wire format."""
    key = (fnum << 3) | wtype
    res = bytearray(encode_varint(key))
    if wtype == 0:
        res.extend(encode_varint(val))
    elif wtype == 2:
        res.extend(encode_varint(len(val)))
        res.extend(val)
    return bytes(res)


def truncate_text_slice(b: bytes, max_head: int = 300, max_tail: int = 100, marker_tag: str = "CodeContent") -> bytes:
    """Truncates a byte slice keeping head and tail."""
    if len(b) <= max_head + max_tail + 50:
        return b
    head = b[:max_head]
    tail = b[-max_tail:]
    marker = f"\n... [{marker_tag} truncated by agydoc to preserve tokens] ...\n".encode("utf-8")
    return head + marker + tail


def prune_tool_payload(payload: bytes, max_output_chars: int = 500) -> bytes:
    """
    Performs deep pruning on a step payload:
    1. For Step 132 (Tool execution result):
       - Field 140 Subfield 2 (Tool output response) -> truncate if > max_output_chars
       - Field 140 Subfield 1 (Tool arguments / CodeContent) -> truncate if > 1000 bytes
       - Field 5 Subfield 4 (Execution call record JSON) -> truncate if > 1000 bytes
    2. For Step 15 (Planner response):
       - Field 20 Subfield 7 (Proposed tool call JSON) -> truncate if > 1500 bytes
    """
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

    # Case A: Tool Execution Step (step_type == 132)
    if stype_val == 132:
        for fnum, wtype, val in fields:
            # Field 5: tool call record
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

            # Field 140: tool result and argument echo
            elif fnum == 140 and wtype == 2 and len(val) > 1000:
                sub = decode_fields(val)
                new_sub = bytearray()
                sub_mod = False
                for sfnum, sfwtype, sfval in sub:
                    # Subfield 1: args
                    if sfnum == 1 and sfwtype == 2 and len(sfval) > 1000:
                        trun = truncate_text_slice(sfval, max_head=250, max_tail=80, marker_tag="CodeContent Arg")
                        new_sub.extend(encode_field(sfnum, sfwtype, trun))
                        sub_mod = True
                    # Subfield 2: output body
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

    # Case B: Historical Planner Step (step_type == 15)
    elif stype_val == 15:
        for fnum, wtype, val in fields:
            if fnum == 20 and wtype == 2 and len(val) > 2500:
                sub = decode_fields(val)
                new_sub = bytearray()
                sub_mod = False
                for sfnum, sfwtype, sfval in sub:
                    # sf 7 is the tool proposal containing full CodeContent
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
