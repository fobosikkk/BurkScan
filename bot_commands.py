import re
from typing import Optional, Set
import json, os
import discord
from discord import app_commands, Embed, Colour
from core.scanner import scan_ip_mc
from core.masscan import run_masscan_cidr
from core.raw_ping import ping_server_raw
import core.db as db


with open("messages.json", "r", encoding="utf-8") as f:
    MSG = json.load(f)

def setup(tree, bot):
    @tree.command(name="scan", description=MSG["scan.description"])
    @app_commands.describe(
        cidr=MSG["scan.describe.cidr"],
        port=MSG["scan.describe.port"],
        rate=MSG["scan.describe.rate"],
        versions=MSG["scan.describe.versions"],
        only_online=MSG["scan.describe.only_online"]
    )
    async def scan_cmd(inter: discord.Interaction, cidr: str,
                       port: Optional[int] = 25565,
                       rate: Optional[int] = 1000,
                       versions: Optional[str] = None,
                       only_online: Optional[bool] = False):
        guild_id = inter.guild_id
        if guild_id is None:
            await inter.response.send_message(MSG["common.server_only"], ephemeral=True)
            return
        versions_set: Optional[Set[str]] = None
        if versions:
            clean = [v for v in re.split(r"[;, ]+", versions) if re.fullmatch(r"\d+\.\d+(?:\.\d+)?", v)]
            if clean:
                versions_set = set(clean)
        await inter.response.send_message(embed=Embed(
            title=MSG["scan.embed.start.title"],
            description=MSG["scan.embed.start.desc"].format(cidr=cidr, port=port, rate=rate),
            colour=Colour.blue()
        ))
        state = await run_masscan_cidr(bot, guild_id, cidr, port, rate)
        await db.queue.join()
        embed = Embed(title=MSG["scan.embed.finish.title"], colour=Colour.green())
        embed.add_field(name=MSG["scan.embed.finish.field_ips"], value=str(len(state.discovered)))
        await inter.followup.send(embed=embed)

    @tree.command(name="scan_ip", description=MSG["scan_ip.description"])
    async def scan_ip_cmd(inter: discord.Interaction, ip: str,
                          versions: Optional[str] = None,
                          only_online: Optional[bool] = False,
                          ports: Optional[str] = None,
                          only_lan: Optional[bool] = False):
        versions_set: Optional[Set[str]] = None
        if versions:
            clean = [v for v in re.split(r"[;, ]+", versions) if re.fullmatch(r"\d+\.\d+(?:\.\d+)?", v)]
            if clean:
                versions_set = set(clean)
        info_embed = discord.Embed(
            title=MSG["scan_ip.embed.start.title"],
            description=MSG["scan_ip.embed.start.desc"].format(ip=ip),
            colour=discord.Colour.blurple()
        )
        info_embed.add_field(name=MSG["scan_ip.embed.start.field_ports"], value=ports if ports else "1-65535", inline=True)
        info_embed.add_field(name=MSG["scan_ip.embed.start.field_versions"], value=", ".join(versions_set) if versions_set else MSG["common.all"], inline=True)
        info_embed.add_field(name=MSG["scan_ip.embed.start.field_only_online"], value=MSG["common.yes"] if only_online else MSG["common.no"], inline=True)
        info_embed.add_field(name=MSG["scan_ip.embed.start.field_only_lan"], value=MSG["common.yes"] if only_lan else MSG["common.no"], inline=True)
        info_embed.set_footer(text=MSG["scan_ip.embed.start.footer"])
        await inter.response.send_message(embed=info_embed)
        results = await scan_ip_mc(ip, versions_set, bool(only_online), ports, bool(only_lan))
        await db.queue.join()
        embed = discord.Embed(title=MSG["scan_ip.embed.finish.title"].format(ip=ip),
                              description=MSG["scan_ip.embed.finish.desc"].format(count=len(results)),
                              colour=discord.Colour.green())
        for port, ok, version, motd, online, mx in results[:10]:
            embed.add_field(
                name=f"{ip}:{port}",
                value=MSG["scan_ip.embed.finish.field_value"].format(version=version, online=online, mx=mx, motd=(motd or "")[:80]),
                inline=False
            )
        if len(results) > 10:
            embed.set_footer(text=MSG["scan_ip.embed.finish.footer"].format(total=len(results)))
        await inter.followup.send(embed=embed)

    @tree.command(name="ping", description=MSG["ping.description"])
    @app_commands.describe(ip=MSG["ping.describe.ip"], port=MSG["ping.describe.port"])
    async def ping_cmd(inter: discord.Interaction, ip: str, port: Optional[int] = 25565):
        await inter.response.defer()
        ok, version, motd, online, mx = await ping_server_raw(ip, port)
        if ok:
            embed = Embed(title=f"✅ {ip}:{port}",
                          description=MSG["ping.embed.ok.desc"].format(version=version, online=online, mx=mx),
                          colour=Colour.green())
            if motd:
                embed.add_field(name="MOTD", value=(motd or "")[:150], inline=False)
        else:
            embed = Embed(title=f"❌ {ip}:{port}",
                          description=MSG["ping.embed.err.desc"].format(error=motd),
                          colour=Colour.red())
        await inter.followup.send(embed=embed)

    @tree.command(name="find", description=MSG["find.description"])
    @app_commands.describe(
        versions=MSG["find.describe.versions"],
        only_online=MSG["find.describe.only_online"],
        motd_contains=MSG["find.describe.motd_contains"]
    )
    async def find_cmd(inter: discord.Interaction,
                       versions: Optional[str] = None,
                       only_online: Optional[bool] = False,
                       motd_contains: Optional[str] = None):
        versions_set: Optional[Set[str]] = None
        if versions:
            clean = [v.strip() for v in re.split(r"[;, ]+", versions) if re.fullmatch(r"\d+\.\d+(?:\.\d+)?", v)]
            if clean:
                versions_set = set(clean)
        rows = db.find_servers_filtered(versions_set, bool(only_online), motd_contains, limit=20)
        if not rows:
            await inter.response.send_message(MSG["find.none"], ephemeral=True)
            return
        embed = discord.Embed(title=MSG["find.embed.title"], colour=discord.Colour.blurple())
        for ip, port, version, motd, online, maxp, last_seen in rows:
            embed.add_field(
                name=f"{ip}:{port}",
                value=MSG["find.embed.field_value"].format(version=version, online=online, maxp=maxp, motd=(motd or "")[:80], last_seen=last_seen),
                inline=False
            )
        await inter.response.send_message(embed=embed)

    @tree.command(name="stats", description=MSG["stats.description"])
    async def stats_cmd(inter: discord.Interaction):
        total, unique_ips, with_online, avg_online, top_server, top_versions, inactive_count, last_seen = db.get_stats()
        await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.playing, name=MSG["common.stored"].format(all=inactive_count+total)))
        embed = discord.Embed(title=MSG["stats.embed.title"], colour=discord.Colour.green())
        embed.add_field(name=MSG["stats.embed.field_total_active"], value=str(total), inline=True)
        embed.add_field(name=MSG["stats.embed.field_inactive"], value=str(inactive_count), inline=True)
        embed.add_field(name=MSG["stats.embed.field_unique_ips"], value=str(unique_ips), inline=True)
        embed.add_field(name=MSG["stats.embed.field_with_online"], value=str(with_online), inline=True)
        embed.add_field(name=MSG["stats.embed.field_avg_online"], value=str(avg_online), inline=True)
        if top_server:
            ip, port, online = top_server
            embed.add_field(name=MSG["stats.embed.field_top_server"], value=f"{ip}:{port} → {online} players", inline=False)
        versions_str = "\n".join([f"{v or '-'}: {c}" for v, c in top_versions]) or "-"
        embed.add_field(name=MSG["stats.embed.field_top_versions"], value=versions_str, inline=False)
        embed.set_footer(text=MSG["stats.embed.footer"].format(last_seen=last_seen))
        await inter.response.send_message(embed=embed)

    @tree.command(name="check_db", description=MSG["check_db.description"])
    @app_commands.describe(
        check_inactive=MSG["check_db.describe.check_inactive"],
        check_whitelisted=MSG["check_db.describe.check_whitelisted"],
        timeout=MSG["check_db.describe.timeout"],
        batch=MSG["check_db.describe.batch"]
    )
    async def check_db_cmd(inter: discord.Interaction,
                           check_inactive: Optional[bool] = False,
                           check_whitelisted: Optional[bool] = False,
                           timeout: Optional[int] = 2,
                           batch: Optional[int] = 200):
        await inter.response.defer()
        await db.check_database(inter, batch_size=batch, timeout=timeout, check_inactive=check_inactive)
