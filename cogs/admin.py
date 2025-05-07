import discord
from discord.ext import commands
from discord import app_commands
import subprocess
from logger import get_logger

log = get_logger(__name__)

ADMIN_ID = 460490189408829441

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        log.info("Admin Modul geladen")

    @app_commands.command(name="sync", description="Synchronisiert die Slash Commands.")
    async def sync(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.bot.tree.sync()
        await interaction.followup.send("Slash Commands wurden synchronisiert!", ephemeral=True)

    @app_commands.command(name="restart", description="Bot Dienst neu starten (Admin only)")
    async def restart(self, interaction: discord.Interaction):
        if interaction.user.id != ADMIN_ID:
            await interaction.response.send_message("Nur Admins dürfen das.", ephemeral=True)
            return

        await interaction.response.send_message("Starte den Bot neu...", ephemeral=True)
        subprocess.Popen(["sudo", "systemctl", "restart", "bot.service"])

async def setup(bot):
    await bot.add_cog(Admin(bot))