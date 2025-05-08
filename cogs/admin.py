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
        log.info("Admin module loaded")

    @app_commands.command(name="sync", description="Synchronize the slash commands.")
    async def sync(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.bot.tree.sync()
        await interaction.followup.send("Slash commands have been synchronized!", ephemeral=True)

    @app_commands.command(name="restart", description="Restart the bot service (Admin only)")
    async def restart(self, interaction: discord.Interaction):
        if interaction.user.id != ADMIN_ID:
            await interaction.response.send_message("Only admins are allowed to do this.", ephemeral=True)
            return

        await interaction.response.send_message("Restarting the bot...", ephemeral=True)
        subprocess.Popen(["sudo", "systemctl", "restart", "bot.service"])

    @app_commands.command(name="feedback", description="Send feedback (will be created as a GitHub issue)")
    @app_commands.describe(message="Describe your feedback")
    async def feedback(self, interaction: discord.Interaction, message: str):
        await interaction.response.defer(ephemeral=True)

        # Create the GitHub issue
        url = f"https://api.github.com/repos/{GITHUB_REPO}/issues"
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
        }
        data = {
            "title": f"Feedback from {interaction.user.name}",
            "body": f"**From:** {interaction.user.mention} (`{interaction.user.id}`)\n\n**Feedback:**\n{message}"
        }

        response = requests.post(url, headers=headers, json=data)

        if response.status_code == 201:
            issue_url = response.json()["html_url"]
            await interaction.followup.send(f"✅ Your feedback has been created: {issue_url}", ephemeral=True)
            log.info(f"Feedback issue created: {issue_url}")
        else:
            await interaction.followup.send("❌ Error while creating the feedback issue.", ephemeral=True)
            log.error(f"Error while creating GitHub issue: {response.status_code} {response.text}")


async def setup(bot):
    await bot.add_cog(Admin(bot))