import discord
from discord.ext import commands
from discord import app_commands
import os
import sys
import asyncio
from helper.card_emojis import CardEmojiManager
from helper.db import Database
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
    # Event triggered when the bot is ready
    log.info(f"Bot is ready → {bot.user}")

    if not hasattr(bot, "card_emojis"):
        # Load card emojis if not already loaded
        from helper.card_emojis import CardEmojiManager
        bot.card_emojis = CardEmojiManager(bot)
        try:
            await bot.card_emojis.load()
            log.info("Card emojis loaded successfully.")
        except Exception as e:
            # Log and handle unexpected errors during emoji loading
            log.error(f"Error loading card emojis: {e}")

async def load_extensions():
    # Dynamically load all extensions (cogs) from the "cogs" directory
    try:
        for filename in os.listdir("./cogs"):
            if filename.endswith(".py"):
                await bot.load_extension(f"cogs.{filename[:-3]}")
        log.info("All extensions loaded successfully.")
    except Exception as e:
        # Log and handle unexpected errors during extension loading
        log.error(f"Error loading extensions: {e}")

async def run_bot():

    try:
        bot.db = Database()
        bot.db.setup_tables()
        log.info("Database initialized and tables ensured.")
    except Exception as e:
        log.error(f"Failed to initialize database: {e}")
        return  # Verhindere, dass der Bot ohne DB weiterläuft

    async with bot:
        await load_extensions()
        await bot.start(DISCORDBOT_TOKEN)

# -----------------------------------------
# 🔧 CLI ENTRYPOINT FOR SYNCING SLASH COMMANDS
# Usage: python bot.py sync
# -----------------------------------------

async def sync_commands():
    # Globally sync all slash commands without running the bot
    try:
        await bot.login(DISCORDBOT_TOKEN)
        await load_extensions()  # Ensure all app_commands are loaded
        synced = await bot.tree.sync()
        log.info(f"Synced {len(synced)} global slash commands.")
    except Exception as e:
        # Log and handle unexpected errors during command syncing
        log.error(f"Failed to sync commands: {e}")
    finally:
        await bot.close()

# -----------------------------------------
# Main entry point for running or syncing the bot
# -----------------------------------------

if __name__ == "__main__":
    discord.utils.setup_logging()  # Set up logging for Discord

    if "sync" in sys.argv:
        # Sync commands if "sync" argument is provided
        asyncio.run(sync_commands())
    else:
        # Run the bot otherwise
        asyncio.run(run_bot())