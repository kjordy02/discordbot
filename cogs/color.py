import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import os
import random
from datetime import datetime

class Color(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.color_roles = ["rot", "blau", "gelb", "grün", "orange", "lila", "pink"]
        self.daily_users_file = "daily_users.json"
        self.daily_users = self.load_daily_users()
        self.change_colors_daily.start()

    def load_daily_users(self):
        if os.path.exists(self.daily_users_file):
            with open(self.daily_users_file, "r") as f:
                return json.load(f)
        return []

    def save_daily_users(self):
        with open(self.daily_users_file, "w") as f:
            json.dump(self.daily_users, f)

    @commands.Cog.listener()
    async def on_ready(self):
        print("Color Modul geladen")

    @app_commands.command(name="dailycolor", description="Toggles den täglichen Farbwechsel für dich.")
    async def dailycolor(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        if user_id in self.daily_users:
            self.daily_users.remove(user_id)
            await interaction.response.send_message("Täglicher Farbwechsel deaktiviert.", ephemeral=True)
        else:
            self.daily_users.append(user_id)
            await interaction.response.send_message("Täglicher Farbwechsel aktiviert.", ephemeral=True)
        self.save_daily_users()

    @tasks.loop(minutes=1)
    async def change_colors_daily(self):
        now = datetime.now()
        if now.hour == 0 and now.minute == 1:
            for guild in self.bot.guilds:
                for member in guild.members:
                    if member.bot:
                        continue
                    if str(member.id) not in self.daily_users:
                        continue

                    current_roles = [role.name for role in member.roles if role.name in self.color_roles]
                    possible_roles = [r for r in self.color_roles if r not in current_roles]

                    if possible_roles:
                        new_role_name = random.choice(possible_roles)
                        new_role = discord.utils.get(guild.roles, name=new_role_name)
                        if new_role:
                            for role in member.roles:
                                if role.name in self.color_roles:
                                    await member.remove_roles(role)
                            await member.add_roles(new_role)

    @change_colors_daily.before_loop
    async def before(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(Color(bot))