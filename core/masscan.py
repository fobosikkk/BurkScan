import asyncio, os, json, datetime
from typing import Set
import config
from core.state import ScanState, scan_states
from core.utils import extract_versions
from core.raw_ping import ping_server_raw
import core.db as db

async def tail_results_file(bot, guild_id: int, json_path: str, port: int, NOTIFY_CHANNEL_ID: int):
    state = scan_states[guild_id]
    for _ in range(100):
        if os.path.exists(json_path): break
        await asyncio.sleep(0.1)
    if not os.path.exists(json_path): return
    seen: Set[str] = set()
    guild = bot.get_guild(guild_id)
    if not guild:
        try:
            guild = await bot.fetch_guild(guild_id)
        except Exception:
            return
    with open(json_path, "r", encoding="utf-8") as f:
        f.seek(0, os.SEEK_SET)
        while state.running or not f.tell() == os.fstat(f.fileno()).st_size:
            pos = f.tell()
            line = f.readline()
            if not line:
                await asyncio.sleep(0.2); f.seek(pos); continue
            try:
                obj = json.loads(line.strip()); ip = obj.get("ip")
            except:
                continue
            if not ip or ip in seen:
                continue
            seen.add(ip)
            ok, version_name, motd, online, mx = await ping_server_raw(ip, port)
            if not ok:
                continue
            db.save_server(ip, port, version_name, motd, online, mx)
            if state.versions_set and not (extract_versions(version_name) & state.versions_set):
                continue
            if state.only_online and online <= 0:
                continue

async def run_masscan_cidr(bot, guild_id: int, cidr: str, port: int, rate: int) -> ScanState:
    state = scan_states.setdefault(guild_id, ScanState())
    timestamp = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(config.OUTPUT_DIR, f"guild_{guild_id}_{timestamp}")
    os.makedirs(out_dir, exist_ok=True)
    json_path = os.path.join(out_dir, "results.json")
    log_path = os.path.join(out_dir, "scan.log")
    state.running = True; state.start_time = datetime.datetime.utcnow()
    state.mode, state.cidr, state.port, state.rate = "cidr", cidr, port, rate
    state.out_dir, state.out_json_path, state.log_path = out_dir, json_path, log_path
    state.discovered.clear()
    cmd = config.MASSCAN_CMD + [cidr, f"-p{port}", f"--rate={rate}",
        "--output-format", "json", "--output-filename", json_path, "--exclude", "255.255.255.255"]
    print(" ".join(cmd))
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE,
                                               stderr=asyncio.subprocess.STDOUT)
    state.process = proc
    asyncio.create_task(tail_results_file(bot, guild_id, json_path, port, config.NOTIFY_CHANNEL_ID))
    with open(log_path, "a", encoding="utf-8", buffering=1) as lf:
        lf.write(f"[start] {datetime.datetime.utcnow().isoformat()}Z | {' '.join(cmd)}\n")
        async for raw in proc.stdout:
            lf.write(raw.decode("utf-8", errors="ignore").rstrip() + "\n")
        rc = await proc.wait()
        lf.write(f"[exit] code={rc} at {datetime.datetime.utcnow().isoformat()}Z\n")
    state.running, state.process = False, None
    if os.path.exists(json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    ip = json.loads(line).get("ip")
                    if ip:
                        state.discovered.add(ip)
                except:
                    pass
    return state
