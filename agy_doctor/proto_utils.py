"""
Protobuf wire-format parser and safe inspector.
Zero aggressive truncation: preserves 100% of code, prompts, thoughts, and file contents.
"""

def decode_fields(b: bytes):
    """
    Decodes raw protobuf wire-format bytes into a list of (field_num, wire_type, value).
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


def prune_tool_payload(payload: bytes, max_output_chars: int = 5000) -> bytes:
    """
    Safe no-op / conservative inspection.
    Guarantees zero loss of user code, assistant reasoning, or history.
    """
    return payload
