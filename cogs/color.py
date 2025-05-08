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
        self.color_roles = {
            "red": discord.Color.from_rgb(220, 20, 60),
            "blue": discord.Color.from_rgb(30, 144, 255),
            "yellow": discord.Color.from_rgb(255, 215, 0),
            "green": discord.Color.from_rgb(50, 205, 50),
            "orange": discord.Color.from_rgb(255, 140, 0),
            "purple": discord.Color.from_rgb(147, 112, 219),
            "pink": discord.Color.from_rgb(255, 105, 180),
            "cyan": discord.Color.from_rgb(0, 255, 255),
            "lime": discord.Color.from_rgb(0, 255, 0),
            "magenta": discord.Color.from_rgb(255, 0, 255),
        }
        self.daily_users_file = os.path.join(SAVE_FOLDER, "daily_users.json")
        self.daily_users = self.load_daily_users()
        self.change_colors_hourly.start()

    def load_daily_users(self):
        if os.path.exists(self.daily_users_file):
            with open(self.daily_users_file, "r") as f:
                try:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
                except json.JSONDecodeError:
                    pass
        return {}

    def save_daily_users(self):
        with open(self.daily_users_file, "w") as f:
            json.dump(self.daily_users, f)

    @commands.Cog.listener()
    async def on_ready(self):
        log.info("Color module loaded")
        for guild in self.bot.guilds:
            await self.ensure_color_roles(guild)

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        await self.ensure_color_roles(guild)

    @app_commands.command(name="colorchange", description="Toggle automatic color change for yourself.")
    async def colorchange(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)
        user_id = str(interaction.user.id)

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
            return

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

                current_roles = [role.name for role in member.roles if role.name in self.color_roles]
                current_color = current_roles[0] if current_roles else None

                possible_colors = [color for color in self.color_roles if color != current_color]
                new_color = random.choice(possible_colors)
                new_role = discord.utils.get(guild.roles, name=new_color)

                if new_role:
                    for role in member.roles:
                        if role.name in self.color_roles:
                            await member.remove_roles(role)

                    await member.add_roles(new_role)
                    log.info(f"[Color] {member.display_name} → {new_color}")

    @change_colors_hourly.before_loop
    async def before(self):
        await self.bot.wait_until_ready()

    async def ensure_color_roles(self, guild: discord.Guild):
        existing_roles = {role.name: role for role in guild.roles}
        bot_member = guild.me

        # Bot's top role (to insert just below it)
        try:
            target_position = bot_member.top_role.position - 1
        except AttributeError:
            target_position = 1

        for role_name, color in self.color_roles.items():
            if role_name in existing_roles:
                continue

            try:
                new_role = await guild.create_role(
                    name=role_name,
                    color=color,
                    reason="Auto-created color role",
                )
                log.info(f"[Color] Created missing role '{role_name}' in guild '{guild.name}'")

                await new_role.edit(position=target_position)

            except discord.Forbidden:
                log.warning(f"[Color] Missing permissions to create/move role '{role_name}' in guild '{guild.name}'")
            except Exception as e:
                log.error(f"[Color] Failed to create role '{role_name}' in guild '{guild.name}': {e}")

async def setup(bot):
    await bot.add_cog(Color(bot))