import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import os
import random
from datetime import datetime
from logger import get_logger
from config import SAVE_FOLDER

log = get_logger(__name__)

class Color(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.color_roles = ["red", "blue", "yellow", "green", "orange", "purple", "pink"]
        self.daily_users_file = os.path.join(SAVE_FOLDER, "daily_users.json")
        self.daily_users = self.load_daily_users()
        self.change_colors_hourly.start()

    def load_daily_users(self):
        """Loads the user file or creates a new one if invalid."""
        if os.path.exists(self.daily_users_file):
            with open(self.daily_users_file, "r") as f:
                try:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
                    else:
                        return {}
                except json.JSONDecodeError:
                    return {}
        return {}

    def save_daily_users(self):
        """Saves the user file."""
        with open(self.daily_users_file, "w") as f:
            json.dump(self.daily_users, f)

    @commands.Cog.listener()
    async def on_ready(self):
        log.info("Color module loaded")

    @app_commands.command(name="colorchange", description="Toggle automatic color change for yourself.")
    async def colorchange(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)
        user_id = str(interaction.user.id)

        # Initialize if not present
        if guild_id not in self.daily_users:
            self.daily_users[guild_id] = []

        if user_id in self.daily_users[guild_id]:
            self.daily_users[guild_id].remove(user_id)
            await interaction.response.send_message("Color change disabled.", ephemeral=True)
        else:
            self.daily_users[guild_id].append(user_id)
            await interaction.response.send_message("Color change enabled.", ephemeral=True)

        self.save_daily_users()

    @tasks.loop(minutes=1)
    async def change_colors_hourly(self):
        now = datetime.now()
        if now.minute != 0:
            return  # Only run on the full hour

        log.info(f"[Color] Starting color rotation for hour {now.hour}")

        for guild in self.bot.guilds:
            guild_id = str(guild.id)
            if guild_id not in self.daily_users:
                continue

            for member in guild.members:
                if member.bot:
                    continue

                user_id = str(member.id)
                if user_id not in self.daily_users[guild_id]:
                    continue

                # Get current color role
                current_roles = [role.name for role in member.roles if role.name in self.color_roles]
                current_color = current_roles[0] if current_roles else None

                # Pick a new color (different from current)
                possible_colors = [color for color in self.color_roles if color != current_color]
                new_color = random.choice(possible_colors)

                # Get the new role
                new_role = discord.utils.get(guild.roles, name=new_color)

                if new_role:
                    # Remove all color roles
                    for role in member.roles:
                        if role.name in self.color_roles:
                            await member.remove_roles(role)

                    # Add the new role
                    await member.add_roles(new_role)
                    log.info(f"[Color] {member.display_name} → {new_color}")

    @change_colors_hourly.before_loop
    async def before(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(Color(bot))