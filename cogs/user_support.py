import discord
from discord.ext import commands
from discord import app_commands
import requests
from logger import get_logger
from config import GITHUB_REPO, GITHUB_TOKEN

log = get_logger(__name__)

class UserSupport(commands.Cog):
    ## Cog for user feedback, bug reporting, and help commands

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        log.info("UserSupport module loaded.")

    @app_commands.command(name="givefeedback", description="Send feedback to the bot maintainers.")
    @app_commands.describe(message="Describe your feedback")
    async def give_feedback(self, interaction: discord.Interaction, message: str):
        await self.create_github_issue(interaction, message, label="feedback")

    @app_commands.command(name="reportbug", description="Report a bug you encountered.")
    @app_commands.describe(message="Describe the bug you encountered")
    async def report_bug(self, interaction: discord.Interaction, message: str):
        await self.create_github_issue(interaction, message, label="bug")

    @app_commands.command(name="help", description="Display general help information.")
    async def help_command(self, interaction: discord.Interaction):
        # Sends a help message listing all available commands
        help_text = (
            "Available Commands:\n"
            "/givefeedback - Submit general suggestions or thoughts.\n"
            "/reportbug - Report an issue or malfunction.\n"
            "/help - Show this help message."
        )
        try:
            # Send the help message as an ephemeral response
            await interaction.response.send_message(help_text, ephemeral=True)
            log.info(f"Help command executed by {interaction.user.name}.")
        except Exception as e:
            # Log and handle unexpected errors
            log.error(f"Error sending help message: {e}")
            await interaction.response.send_message("An error occurred while displaying the help message.", ephemeral=True)

    async def create_github_issue(self, interaction: discord.Interaction, message: str, label: str):
        # Creates a GitHub issue for feedback or bug reports
        await interaction.response.defer(ephemeral=True)

        # Prepare the GitHub API request
        url = f"https://api.github.com/repos/{GITHUB_REPO}/issues"
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
        }
        data = {
            "title": f"{label.title()} from {interaction.user.name}",
            "body": f"From: {interaction.user.name}\n\n{label.title()}:\n{message}",
            "labels": [label]
        }

        try:
            # Send the request to create the GitHub issue
            response = requests.post(url, headers=headers, json=data)
            if response.status_code == 201:
                # Issue created successfully
                issue_url = response.json().get("html_url", "")
                await interaction.followup.send(f"Your {label} has been submitted.", ephemeral=True)
                log.info(f"GitHub issue created successfully: {issue_url}")
            else:
                # Log the error if the issue creation fails
                log.error(f"Failed to create GitHub issue. Status: {response.status_code}, Response: {response.text}")
                await interaction.followup.send(f"Failed to submit {label}. Please try again later.", ephemeral=True)
        except Exception as e:
            # Log and handle unexpected errors
            log.error(f"Exception occurred while creating GitHub issue: {e}")
            await interaction.followup.send("An unexpected error occurred while submitting your request.", ephemeral=True)

async def setup(bot: commands.Bot):
    # Adds the UserSupport cog to the bot
    try:
        await bot.add_cog(UserSupport(bot))
        log.info("UserSupport cog successfully added to the bot.")
    except Exception as e:
        # Log and handle unexpected errors during setup
        log.error(f"Error setting up UserSupport cog: {e}")