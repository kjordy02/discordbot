import discord
from discord.ext import commands
from discord import app_commands
import subprocess
import requests
from logger import get_logger
from config import ADMIN_ID, GITHUB_REPO, GITHUB_TOKEN

log = get_logger(__name__)

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

    @app_commands.command(name="feedback", description="Sende Feedback (wird als GitHub Ticket erstellt)")
    @app_commands.describe(message="Beschreibe dein Feedback")
    async def feedback(self, interaction: discord.Interaction, message: str):
        await interaction.response.defer(ephemeral=True)

        # Erstelle das GitHub Issue
        url = f"https://api.github.com/repos/{GITHUB_REPO}/issues"
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
        }
        data = {
            "title": f"Feedback von {interaction.user.name}",
            "body": f"**Von:** {interaction.user.mention} (`{interaction.user.id}`)\n\n**Feedback:**\n{message}"
        }

        response = requests.post(url, headers=headers, json=data)

        if response.status_code == 201:
            issue_url = response.json()["html_url"]
            await interaction.followup.send(f"✅ Dein Feedback wurde erstellt: {issue_url}", ephemeral=True)
            log.info(f"Feedback Issue erstellt: {issue_url}")
        else:
            await interaction.followup.send("❌ Fehler beim Erstellen des Feedback-Issues.", ephemeral=True)
            log.error(f"Fehler beim Erstellen des GitHub Issues: {response.status_code} {response.text}")


async def setup(bot):
    await bot.add_cog(Admin(bot))