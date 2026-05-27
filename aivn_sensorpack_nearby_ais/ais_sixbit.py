"""Helpers for AIS 6-bit armoring."""


def payload_to_bits(payload: str, fill_bits: int) -> str:
    bits = "".join(_char_to_sixbit(ch) for ch in payload)
    if fill_bits:
        bits = bits[:-fill_bits]
    return bits


def get_uint(bits: str, start: int, length: int) -> int:
    return int(bits[start:start + length], 2)


def get_int(bits: str, start: int, length: int) -> int:
    raw = bits[start:start + length]
    value = int(raw, 2)
    if raw and raw[0] == "1":
        value -= 1 << length
    return value


def get_text(bits: str, start: int, length: int) -> str:
    out = []
    for offset in range(start, start + length, 6):
        code = get_uint(bits, offset, 6)
        if code < 32:
            out.append(chr(code + 64))
        else:
            out.append(chr(code))
    return "".join(out).replace("@", "").strip()


def _char_to_sixbit(ch: str) -> str:
    value = ord(ch) - 48
    if value > 40:
        value -= 8
    return f"{value:06b}"
