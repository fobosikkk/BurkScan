import discord
import asyncio

varss = """DEFAULT_PORT = 25565
DEFAULT_RATE = 1000
PING_TIMEOUT = 2.5
PING_WORKERS = 100
RESULTS_SHOW_LIMIT = 15
"""

print("Welcome to BrukScan setup\nThis script will create config.py for you\n\n")

async def check_token(token: str) -> bool:
    try:
        client = discord.Client(intents=discord.Intents.none())

        @client.event
        async def on_ready():
            print(f"✅ Logged in as {client.user}")
            await client.close()

        await client.start(token)
        return True
    except Exception as e:
        print(f"❌ Invalid token: {e}")
        return False

token = input("Please enter your Discord token: ")

asyncio.run(check_token(token))

masscan_dir = input("Please enter your masscan directory (ex. C:\\Users\\fobos\\Documents\\Coding\\masscan\\masscan-1.3.1.exe): ")

with open("config.py", "w", encoding="utf-8") as f:
    f.write(f'DISCORD_TOKEN = "{token}"\n')
    f.write(f'MASSCAN_CMD = [r"{masscan_dir}"]\n\n')
    f.write(varss)

print("✅ config.py created successfully! Now run bot.py")