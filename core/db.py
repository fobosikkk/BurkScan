import sqlite3
import datetime
import asyncio
from typing import Optional
from core.raw_ping import ping_server_raw
import discord, json, os

DB_PATH = "servers.db"

MESSAGES_PATH = os.getenv("MESSAGES_JSON_PATH", "messages.json")
with open(MESSAGES_PATH, "r", encoding="utf-8") as f:
    MSG = json.load(f)

queue: asyncio.Queue = asyncio.Queue()
conn = None

def init_db():
    global conn
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS servers(
        ip TEXT,
        port INTEGER,
        version TEXT,
        motd TEXT,
        online INTEGER,
        max_players INTEGER,
        last_seen TIMESTAMP,
        inactive INTEGER,
        whitelisted INTEGER DEFAULT 0,
        PRIMARY KEY (ip, port)
    )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS inactive_servers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip TEXT NOT NULL,
            port INTEGER NOT NULL,
            last_checked TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ip, port)
        )
        """)
    conn.commit()

async def db_writer():
    global conn
    cur = conn.cursor()
    while True:
        ip, port, version, motd, online, maxp = await queue.get()
        try:
            cur.execute("""
            INSERT INTO servers (ip, port, version, motd, online, max_players, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ip, port) DO UPDATE SET
                version=excluded.version,
                motd=excluded.motd,
                online=excluded.online,
                max_players=excluded.max_players,
                last_seen=excluded.last_seen
            """, (ip, port, version, motd, online, maxp, datetime.datetime.utcnow()))
            conn.commit()
        except Exception as e:
            print(f"[DB ERROR] {e}")
        finally:
            queue.task_done()

def save_server(ip, port, version, motd, online, maxp):
    try:
        queue.put_nowait((ip, port, version, motd, online, maxp))
    except asyncio.QueueFull:
        print("⚠️")

def get_servers(limit: int = 50):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT ip, port, version, motd, online, max_players, last_seen FROM servers ORDER BY last_seen DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows

def get_stats():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM servers")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT ip) FROM servers")
    unique_ips = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM servers WHERE online > 0")
    with_online = cur.fetchone()[0]
    cur.execute("SELECT AVG(online) FROM servers WHERE online > 0")
    avg_online = round(cur.fetchone()[0] or 0, 2)
    cur.execute("SELECT ip, port, online FROM servers ORDER BY online DESC LIMIT 1")
    top_server = cur.fetchone()
    cur.execute("SELECT version, COUNT(*) FROM servers GROUP BY version ORDER BY COUNT(*) DESC LIMIT 5")
    top_versions = cur.fetchall()
    cur.execute("SELECT COUNT(*) FROM inactive_servers")
    inactive_count = cur.fetchone()[0]
    cur.execute("SELECT MAX(last_seen) FROM servers")
    last_seen = cur.fetchone()[0]
    conn.close()
    return total, unique_ips, with_online, avg_online, top_server, top_versions, inactive_count, last_seen

def find_servers_filtered(
    versions: Optional[set[str]] = None,
    only_online: bool = False,
    motd_contains: Optional[str] = None,
    limit: int = 50
):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    query = "SELECT ip, port, version, motd, online, max_players, last_seen FROM servers WHERE 1=1"
    params = []
    if versions:
        placeholders = ",".join("?" * len(versions))
        query += f" AND version IN ({placeholders})"
        params.extend(list(versions))
    if only_online:
        query += " AND online > 0"
    if motd_contains:
        query += " AND motd LIKE ?"
        params.append(f"%{motd_contains}%")
    query += " ORDER BY last_seen DESC LIMIT ?"
    params.append(limit)
    cur.execute(query, tuple(params))
    rows = cur.fetchall()
    conn.close()
    return rows

async def check_database(inter: discord.Interaction,
                         batch_size: int = 200,
                         timeout: float = 1.5,
                         check_inactive: bool = False):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT ip, port FROM servers")
    servers = cur.fetchall()
    conn.close()
    total = len(servers)
    ok_count, inactive_count, revived_count, deleted_count = 0, 0, 0, 0
    async def check_one(ip, port):
        nonlocal ok_count, inactive_count
        try:
            ok, version_name, motd, online, maxp = await asyncio.wait_for(
                ping_server_raw(ip, port), timeout=timeout
            )
        except asyncio.TimeoutError:
            ok = False
        if ok:
            save_server(ip, port, version_name, motd, online, maxp)
            ok_count += 1
        else:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("""
            INSERT INTO inactive_servers (ip, port, last_checked)
            VALUES (?, ?, ?)
            ON CONFLICT(ip, port) DO UPDATE SET last_checked=?
            """, (ip, port, datetime.datetime.utcnow(), datetime.datetime.utcnow()))
            conn.commit()
            conn.close()
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("DELETE FROM servers WHERE ip=? AND port=?", (ip, port))
            conn.commit()
            conn.close()
            inactive_count += 1
    embed = discord.Embed(
        title=MSG["check_db.embed.start.title"],
        description=MSG["check_db.embed.start.desc"],
        colour=discord.Colour.orange()
    )
    msg = await inter.followup.send(embed=embed, wait=True)
    for i in range(0, total, batch_size):
        batch = servers[i:i+batch_size]
        await asyncio.gather(*[asyncio.create_task(check_one(ip, port)) for ip, port in batch])
        done = i + len(batch)
        percent = done / total if total else 1
        bar = "█" * int(20*percent) + "—" * (20-int(20*percent))
        embed = discord.Embed(
            title=MSG["check_db.embed.progress.title"],
            description=MSG["check_db.embed.progress.desc"].format(done=done, total=total),
            colour=discord.Colour.orange()
        )
        embed.add_field(name=MSG["check_db.embed.progress.field_bar"], value=f"[{bar}] {percent:.0%}", inline=False)
        embed.add_field(name=MSG["check_db.embed.progress.field_active"], value=str(ok_count), inline=True)
        embed.add_field(name=MSG["check_db.embed.progress.field_inactive"], value=str(inactive_count), inline=True)
        await msg.edit(embed=embed)
    if check_inactive:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT ip, port, last_checked FROM inactive_servers")
        inactive_list = cur.fetchall()
        conn.close()
        total_inactive = len(inactive_list)
        async def check_inactive_one(ip, port, last_checked):
            nonlocal revived_count
            try:
                ok, version_name, motd, online, maxp = await asyncio.wait_for(
                    ping_server_raw(ip, port), timeout=timeout
                )
            except asyncio.TimeoutError:
                ok = False
            if ok:
                save_server(ip, port, version_name, motd, online, maxp)
                revived_count += 1
                conn = sqlite3.connect(DB_PATH)
                cur = conn.cursor()
                cur.execute("DELETE FROM inactive_servers WHERE ip=? AND port=?", (ip, port))
                conn.commit()
                conn.close()
        for i in range(0, total_inactive, batch_size):
            batch = inactive_list[i:i+batch_size]
            await asyncio.gather(*[
                asyncio.create_task(check_inactive_one(ip, port, last_checked))
                for ip, port, last_checked in batch
            ])
            done = i + len(batch)
            percent = done / total_inactive if total_inactive else 1
            bar = "█" * int(20*percent) + "—" * (20-int(20*percent))
            embed = discord.Embed(
                title=MSG["check_db.embed.inactive.title"],
                description=MSG["check_db.embed.inactive.desc"].format(done=done, total=total_inactive),
                colour=discord.Colour.dark_grey()
            )
            embed.add_field(name=MSG["check_db.embed.inactive.field_bar"], value=f"[{bar}] {percent:.0%}", inline=False)
            embed.add_field(name=MSG["check_db.embed.inactive.field_revived"], value=str(revived_count), inline=True)
            await msg.edit(embed=embed)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM inactive_servers WHERE last_checked < ?",
        (datetime.datetime.utcnow() - datetime.timedelta(days=7),)
    )
    deleted_count = cur.rowcount
    conn.commit()
    conn.close()
    embed = discord.Embed(title=MSG["check_db.embed.finish.title"], colour=discord.Colour.green())
    embed.add_field(name=MSG["check_db.embed.finish.field_active"], value=str(ok_count), inline=True)
    embed.add_field(name=MSG["check_db.embed.finish.field_inactive"], value=str(inactive_count), inline=True)
    embed.add_field(name=MSG["check_db.embed.finish.field_revived"], value=str(revived_count), inline=True)
    embed.add_field(name=MSG["check_db.embed.finish.field_deleted"], value=str(deleted_count), inline=True)
    await msg.edit(embed=embed)
    return ok_count, inactive_count, revived_count, deleted_count
