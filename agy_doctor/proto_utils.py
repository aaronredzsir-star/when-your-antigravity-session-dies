"""
Protobuf wire-format parser and re-encoder without external dependencies.
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
                # Unsupported wire types (1: 64-bit, 5: 32-bit), stop safe parsing
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


def prune_tool_payload(payload: bytes, max_output_chars: int = 500) -> bytes:
    """
    Inspects a step payload. If it is a tool execution result (step_type 132 / Field 140),
    safely truncates the raw output body (Subfield 2) while keeping all metadata,
    file paths, and line numbers 100% intact.
    """
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
                    # Truncate content: head + marker + tail
                    head = sf_val[:max_output_chars]
                    tail = sf_val[-150:]
                    marker = b"\n... [Output pruned by antigravity-doctor for context optimization] ...\n"
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
