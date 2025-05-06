import discord
from discord.ext import commands
import os

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.presences = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Bot ist bereit → {bot.user}")

    for guild in bot.guilds:
        await bot.tree.sync(guild=guild)
        print(f"Slash Commands für {guild.name} synchronisiert!")

async def load_extensions():
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py"):
            await bot.load_extension(f"cogs.{filename[:-3]}")

async def main():
    async with bot:
        await load_extensions()
        await bot.start("NTM0NDY0NjIyNDUxNzUyOTcw.GuQX8M.DA4Cn8U7_eFdzpbTEyY6emi9F7ocO1OrGTFiEU")

import asyncio
asyncio.run(main())