"""ECS nearby ship parser for !PNSD sentences."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


POWER_SOURCE_LOOKUP = {0: "POE", 1: "Battery"}
COMM_NET_LOOKUP = {
    1: "AIS",
    2: "VPASS",
    3: "LTE-M",
}
SIXBITS_TO_ASCII_LOOKUP = {
    "000000": "@",
    "000001": "A",
    "000010": "B",
    "000011": "C",
    "000100": "D",
    "000101": "E",
    "000110": "F",
    "000111": "G",
    "001000": "H",
    "001001": "I",
    "001010": "J",
    "001011": "K",
    "001100": "L",
    "001101": "M",
    "001110": "N",
    "001111": "O",
    "010000": "P",
    "010001": "Q",
    "010010": "R",
    "010011": "S",
    "010100": "T",
    "010101": "U",
    "010110": "V",
    "010111": "W",
    "011000": "X",
    "011001": "Y",
    "011010": "Z",
    "011011": "[",
    "011100": "\\",
    "011101": "]",
    "011110": "^",
    "011111": "_",
    "100000": " ",
    "100001": "!",
    "100010": '"',
    "100011": "#",
    "100100": "$",
    "100101": "%",
    "100110": "&",
    "100111": "`",
    "101000": "(",
    "101001": ")",
    "101010": "*",
    "101011": "+",
    "101100": ",",
    "101101": "-",
    "101110": ".",
    "101111": "/",
    "110000": "0",
    "110001": "1",
    "110010": "2",
    "110011": "3",
    "110100": "4",
    "110101": "5",
    "110110": "6",
    "110111": "7",
    "111000": "8",
    "111001": "9",
    "111010": ":",
    "111011": ";",
    "111100": "<",
    "111101": "=",
    "111110": ">",
    "111111": "?",
}
ASCII_TO_SIXBITS_LOOKUP = {
    "0": "000000",
    "1": "000001",
    "2": "000010",
    "3": "000011",
    "4": "000100",
    "5": "000101",
    "6": "000110",
    "7": "000111",
    "8": "001000",
    "9": "001001",
    ":": "001010",
    ";": "001011",
    "<": "001100",
    "=": "001101",
    ">": "001110",
    "?": "001111",
    "@": "010000",
    "A": "010001",
    "B": "010010",
    "C": "010011",
    "D": "010100",
    "E": "010101",
    "F": "010110",
    "G": "010111",
    "H": "011000",
    "I": "011001",
    "J": "011010",
    "K": "011011",
    "L": "011100",
    "M": "011101",
    "N": "011110",
    "O": "011111",
    "P": "100000",
    "Q": "100001",
    "R": "100010",
    "S": "100011",
    "T": "100100",
    "U": "100101",
    "V": "100110",
    "W": "100111",
    "`": "101000",
    "a": "101001",
    "b": "101010",
    "c": "101011",
    "d": "101100",
    "e": "101101",
    "f": "101110",
    "g": "101111",
    "h": "110000",
    "i": "110001",
    "j": "110010",
    "k": "110011",
    "l": "110100",
    "m": "110101",
    "n": "110110",
    "o": "110111",
    "p": "111000",
    "q": "111001",
    "r": "111010",
    "s": "111011",
    "t": "111100",
    "u": "111101",
    "v": "111110",
    "w": "111111",
}


@dataclass
class EcsDecoded:
    ship_id: str
    ship_name: str
    ship_type: str
    lat: float
    lon: float
    sog: float
    cog: float
    heading: int
    comm_net: str
    power_source: str
    uc_num: int
    receiving_time_unix: int
    receiving_time_text: str
    original_sentence: str
    parser_type: str = "pnsd"


def parse_ecs_sentence(sentence: str, checksum_required: bool = True) -> EcsDecoded | None:
    raw = (sentence or "").strip()
    if not raw.startswith("!PNSD"):
        return None

    body, checksum = _split_checksum(raw)
    if checksum_required and not _checksum_ok(body, checksum):
        raise ValueError(f"ECS checksum mismatch: {raw}")

    fields = body.split(",")
    if not fields or fields[0] != "!PNSD":
        raise ValueError(f"unsupported ECS sentence: {raw}")
    if len(fields) < 2:
        raise ValueError(f"ECS sentence has too few fields: {raw}")

    encoded = fields[-1]
    return decode_nsd_msg(encoded, raw)


def decode_nsd_msg(encoded_msg: str, original_sentence: str) -> EcsDecoded:
    bit_string = sentence_ascii_to_bit_string(encoded_msg)
    offset = 0

    ship_id_length = int(bit_string[offset:offset + 8], 2)
    offset += 8
    ship_id = decode_ship_id(bit_string[offset:offset + ship_id_length])
    offset += ship_id_length

    comm_net = decode_comm_net(bit_string[offset:offset + 4])
    offset += 4

    lat = decode_signed_scaled(bit_string[offset:offset + 27], 600000.0)
    offset += 27
    lon = decode_signed_scaled(bit_string[offset:offset + 28], 600000.0)
    offset += 28

    sog = int(bit_string[offset:offset + 10], 2) / 10.0
    offset += 10
    cog = int(bit_string[offset:offset + 12], 2) / 10.0
    offset += 12
    heading = int(bit_string[offset:offset + 9], 2)
    offset += 9

    ship_type = decode_sixbit_text(bit_string[offset:offset + 24])
    offset += 24
    uc_num = int(bit_string[offset:offset + 30], 2)
    offset += 30

    receiving_time_unix = int(bit_string[offset:offset + 32], 2)
    offset += 32

    ship_name_length = int(bit_string[offset:offset + 9], 2)
    offset += 9
    ship_name = decode_utf16_text(bit_string[offset:offset + ship_name_length])
    offset += ship_name_length

    power_source = POWER_SOURCE_LOOKUP.get(int(bit_string[offset:offset + 1], 2), "")
    receiving_time_text = datetime.fromtimestamp(
        receiving_time_unix,
        tz=timezone.utc,
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    return EcsDecoded(
        ship_id=ship_id,
        ship_name=ship_name,
        ship_type=ship_type,
        lat=lat,
        lon=lon,
        sog=sog,
        cog=cog,
        heading=heading,
        comm_net=comm_net,
        power_source=power_source,
        uc_num=uc_num,
        receiving_time_unix=receiving_time_unix,
        receiving_time_text=receiving_time_text,
        original_sentence=original_sentence,
    )


def sentence_ascii_to_bit_string(ascii_string: str) -> str:
    bits = []
    for ch in ascii_string:
        sixbits = ASCII_TO_SIXBITS_LOOKUP.get(ch)
        if sixbits is None:
            raise ValueError(f"unsupported ECS payload character: {ch!r}")
        bits.append(sixbits)
    return "".join(bits)


def decode_ship_id(ship_id_bitstring: str) -> str:
    return decode_sixbit_text(ship_id_bitstring)


def decode_comm_net(comm_net_bitstring: str) -> str:
    return COMM_NET_LOOKUP.get(int(comm_net_bitstring, 2), "")


def decode_sixbit_text(bit_string: str) -> str:
    out = []
    for index in range(0, len(bit_string), 6):
        sixbits = bit_string[index:index + 6]
        if len(sixbits) < 6:
            break
        out.append(SIXBITS_TO_ASCII_LOOKUP.get(sixbits, ""))
    return "".join(out).replace("@", "").strip()


def decode_utf16_text(bit_string: str) -> str:
    if not bit_string:
        return ""
    if len(bit_string) % 8 != 0:
        raise ValueError("ECS ship_name bit length must be divisible by 8")
    ship_name_bytes = bytes(
        int(bit_string[i:i + 8], 2)
        for i in range(0, len(bit_string), 8)
    )
    return ship_name_bytes.decode("utf-16be", errors="strict")


def decode_signed_scaled(bit_string: str, scale: float) -> float:
    value = int(bit_string, 2)
    if bit_string and bit_string[0] == "1":
        value -= 1 << len(bit_string)
    return value / scale


def _split_checksum(sentence: str) -> tuple[str, str]:
    star = sentence.rfind("*")
    if star == -1:
        return sentence, ""
    checksum = sentence[star + 1:star + 3]
    return sentence[:star], checksum


def _checksum_ok(body: str, checksum: str) -> bool:
    if not checksum:
        return False
    calc = 0
    for ch in body[1:]:
        calc ^= ord(ch)
    try:
        expected = int(checksum, 16)
    except ValueError:
        return False
    return calc == expected
