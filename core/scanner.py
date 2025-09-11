# scanner.py
import asyncio, re
from typing import Optional, Set, List, Tuple
from core.utils import extract_versions
from core.raw_ping import ping_server_raw
import core.db as db

async def scan_ip_mc(ip: str,
    versions_set: Optional[Set[str]] = None,
    only_online: bool = False,
    ports_range: Optional[str] = None,
    only_lan: bool = False,
    sem_limit: int = 500,
    batch_size: int = 500,
) -> List[Tuple[int, bool, str, str, int, int]]:
    results: List[Tuple[int, bool, str, str, int, int]] = []
    sem = asyncio.Semaphore(sem_limit)
    if ports_range and "-" in ports_range:
        try:
            start, end = map(int, ports_range.split("-", 1))
            start, end = max(1, start), min(65535, end)
        except:
            start, end = 1, 65535
    else:
        start, end = 1, 65535
    async def ping_port(port: int):
        async with sem:
            ok, version_name, motd, online, maxp = await ping_server_raw(ip, port)
            if not ok:
                return
            db.save_server(ip, port, version_name, motd, online, maxp)
            if versions_set and not (extract_versions(version_name) & versions_set):
                return
            if only_online and online <= 0:
                return
            if only_lan and not ((" - " in motd) and maxp == 8):
                return
            results.append((port, ok, version_name, motd, online, maxp))
    for batch_start in range(start, end + 1, batch_size):
        batch_end = min(batch_start + batch_size, end + 1)
        await asyncio.gather(*[ping_port(p) for p in range(batch_start, batch_end)])
    return results
