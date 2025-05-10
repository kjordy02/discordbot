import discord
from discord.ext import commands
import os
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

    for guild in bot.guilds:
        try:
            synced = await bot.tree.sync(guild=guild)
            log.info(f"{len(synced)} Slash commands synchronized for {guild.name}!")
        except Exception as e:
            log.error(f"Failed to sync commands: {e}")


async def load_extensions():
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py"):
            await bot.load_extension(f"cogs.{filename[:-3]}")

async def main():
    async with bot:
        await load_extensions()
        await bot.start(DISCORDBOT_TOKEN)

import asyncio
asyncio.run(main())