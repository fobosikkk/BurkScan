import asyncio, struct, json
from typing import Tuple

def write_varint(value: int) -> bytes:
    out = b""
    while True:
        temp = value & 0b01111111
        value >>= 7
        if value != 0:
            out += struct.pack("B", temp | 0b10000000)
        else:
            out += struct.pack("B", temp)
            break
    return out

async def read_varint(reader: asyncio.StreamReader) -> int:
    num_read, result = 0, 0
    while True:
        byte = await reader.readexactly(1)
        value = byte[0] & 0b01111111
        result |= value << (7 * num_read)
        num_read += 1
        if (byte[0] & 0b10000000) == 0:
            break
        if num_read > 5:
            raise Exception("VarInt too big")
    return result

async def ping_server_raw(ip: str, port: int, timeout: float = 3.0) -> Tuple[bool, str, str, int, int]:
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(ip, port), timeout=timeout)
        host_bytes = ip.encode("utf-8")
        data = b""
        data += write_varint(0x00)
        data += write_varint(47)
        data += write_varint(len(host_bytes)) + host_bytes
        data += struct.pack(">H", port)
        data += write_varint(1)
        packet = write_varint(len(data)) + data
        writer.write(packet); await writer.drain()
        writer.write(b"\x01\x00"); await writer.drain()
        await read_varint(reader)
        packet_id = await read_varint(reader)
        if packet_id != 0x00:
            raise Exception("Invalid packet id")
        str_len = await read_varint(reader)
        data = await reader.readexactly(str_len)
        obj = json.loads(data.decode("utf-8"))
        writer.close(); await writer.wait_closed()
        version = obj.get("version", {}).get("name", "-")
        motd = obj.get("description", "")
        if isinstance(motd, dict):
            motd = motd.get("text", str(motd))
        players = obj.get("players", {})
        return True, version, motd, players.get("online", 0), players.get("max", 0)
    except Exception as e:
        return False, "", f"{type(e).__name__}: {e}", 0, 0

