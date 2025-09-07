from discord.ext import commands
from discord import Intents
import config
import bot_commands
import core.db as db
import asyncio
from discord import Activity, ActivityType
import json

INTENTS = Intents.default()
INTENTS.message_content = True

bot = commands.Bot(command_prefix="!", intents=INTENTS)
tree = bot.tree

bot_commands.setup(tree, bot)

with open("messages.json", "r", encoding="utf-8") as f:
    MSG = json.load(f)


@bot.event
async def on_ready():
    db.init_db()
    asyncio.create_task(db.db_writer())
    await tree.sync()
    print(f"✅ Logged in as {bot.user} (id={bot.user.id})")
    total, unique_ips, with_online, avg_online, top_server, top_versions, inactive_count, last_seen = db.get_stats()
    await bot.change_presence(activity=Activity(type=ActivityType.playing, name=MSG["common.stored"].format(all=inactive_count+total)))

if __name__ == "__main__":
    bot.run(config.DISCORD_TOKEN)
