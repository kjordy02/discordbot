import discord
from discord.ext import commands
from discord import app_commands
import os
import sys
import asyncio
from logger import get_logger
from config import DISCORDBOT_TOKEN

log = get_logger(__name__)

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.presences = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    log.info(f"Bot is ready → {bot.user}")

async def load_extensions():
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py"):
            await bot.load_extension(f"cogs.{filename[:-3]}")

async def run_bot():
    async with bot:
        await load_extensions()
        await bot.start(DISCORDBOT_TOKEN)

# -----------------------------------------
# 🔧 CLI ENTRYPOINT FOR SYNCING SLASH COMMANDS
# Usage: python bot.py sync
# -----------------------------------------

async def sync_commands():
    """Globally sync all slash commands without running the bot."""
    await bot.login(DISCORDBOT_TOKEN)
    await load_extensions()  # Ensure all app_commands are loaded

    try:
        synced = await bot.tree.sync()
        log.info(f"Synced {len(synced)} global slash commands.")
    except Exception as e:
        log.error(f"Failed to sync: {e}")
    await bot.close()

# -----------------------------------------

if __name__ == "__main__":
    discord.utils.setup_logging()

    if "sync" in sys.argv:
        asyncio.run(sync_commands())
    else:
        asyncio.run(run_bot())