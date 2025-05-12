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
    # A cog for managing color roles and automatic color changes for users.

    def __init__(self, bot):
        self.bot = bot
        # Predefined color roles with their RGB values
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
        # File to store users who have enabled automatic color changes
        self.daily_users_file = os.path.join(SAVE_FOLDER, "daily_users.json")
        self.daily_users = self.load_daily_users()  # Load the daily users from the file
        self.change_colors_hourly.start()  # Start the task to change colors hourly

    def load_daily_users(self):
        # Loads the list of users who have enabled automatic color changes from a JSON file.
        # Returns:
        #     dict: A dictionary of guild IDs mapping to lists of user IDs.
        if os.path.exists(self.daily_users_file):
            try:
                with open(self.daily_users_file, "r") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        log.info("Successfully loaded daily users from file.")
                        return data
            except json.JSONDecodeError:
                log.warning("Failed to decode daily_users.json. Resetting data.")
        else:
            log.info("No daily_users.json file found. Starting with an empty list.")
        return {}

    def save_daily_users(self):
        # Saves the list of users who have enabled automatic color changes to a JSON file.
        try:
            with open(self.daily_users_file, "w") as f:
                json.dump(self.daily_users, f)
            log.info("Successfully saved daily users to file.")
        except Exception as e:
            log.error(f"Failed to save daily users to file: {e}")

    @commands.Cog.listener()
    async def on_ready(self):
        # Event listener triggered when the bot is ready.
        # Ensures that all required color roles exist in all guilds.
        log.info("Color module loaded and ready.")
        for guild in self.bot.guilds:
            await self.ensure_color_roles(guild)

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        # Event listener triggered when the bot joins a new guild.
        # Ensures that all required color roles exist in the new guild.
        log.info(f"Joined new guild: {guild.name} (ID: {guild.id}). Ensuring color roles.")
        await self.ensure_color_roles(guild)

    @app_commands.command(name="colorchange", description="Toggle automatic color change for yourself.")
    async def colorchange(self, interaction: discord.Interaction):
        # Toggles automatic color changes for the user who invoked the command.
        guild_id = str(interaction.guild.id)
        user_id = str(interaction.user.id)

        if guild_id not in self.daily_users:
            self.daily_users[guild_id] = []

        if user_id in self.daily_users[guild_id]:
            # Disable color change for the user
            self.daily_users[guild_id].remove(user_id)
            await interaction.response.send_message("Color change disabled.", ephemeral=True)
            log.info(f"Disabled color change for user {interaction.user.display_name} in guild {interaction.guild.name}.")
        else:
            # Enable color change for the user
            self.daily_users[guild_id].append(user_id)
            await interaction.response.send_message("Color change enabled.", ephemeral=True)
            log.info(f"Enabled color change for user {interaction.user.display_name} in guild {interaction.guild.name}.")

        self.save_daily_users()  # Save the updated list of users

    @tasks.loop(minutes=1)
    async def change_colors_hourly(self):
        # Task that runs every minute to check if it's the start of a new hour.
        # If so, rotates the colors for users who have enabled automatic color changes.
        now = datetime.now()
        if now.minute != 0:
            return  # Only run at the start of each hour

        log.info(f"Starting color rotation for hour {now.hour}.")

        for guild in self.bot.guilds:
            guild_id = str(guild.id)
            if guild_id not in self.daily_users:
                continue

            for member in guild.members:
                if member.bot:
                    continue  # Skip bots

                user_id = str(member.id)
                if user_id not in self.daily_users[guild_id]:
                    continue

                # Get the user's current color role
                current_roles = [role.name for role in member.roles if role.name in self.color_roles]
                current_color = current_roles[0] if current_roles else None

                # Choose a new color that is different from the current one
                possible_colors = [color for color in self.color_roles if color != current_color]
                new_color = random.choice(possible_colors)
                new_role = discord.utils.get(guild.roles, name=new_color)

                if new_role:
                    # Remove the current color role and assign the new one
                    for role in member.roles:
                        if role.name in self.color_roles:
                            await member.remove_roles(role)

                    await member.add_roles(new_role)
                    log.info(f"Changed color for {member.display_name} in guild {guild.name}: {new_color}.")

    @change_colors_hourly.before_loop
    async def before(self):
        # Waits until the bot is ready before starting the color rotation task.
        log.info("Waiting for bot to be ready before starting color rotation task.")
        await self.bot.wait_until_ready()

    async def ensure_color_roles(self, guild: discord.Guild):
        # Ensures that all required color roles exist in the specified guild.
        # If a role is missing, it is created and positioned just below the bot's top role.
        existing_roles = {role.name: role for role in guild.roles}
        bot_member = guild.me

        # Determine the position to insert new roles (just below the bot's top role)
        try:
            target_position = bot_member.top_role.position - 1
        except AttributeError:
            target_position = 1

        for role_name, color in self.color_roles.items():
            if role_name in existing_roles:
                continue  # Skip if the role already exists

            try:
                # Create the missing role
                new_role = await guild.create_role(
                    name=role_name,
                    color=color,
                    reason="Auto-created color role",
                )
                log.info(f"Created missing role '{role_name}' in guild '{guild.name}'.")

                # Adjust the role's position
                await new_role.edit(position=target_position)

            except discord.Forbidden:
                log.warning(f"Missing permissions to create/move role '{role_name}' in guild '{guild.name}'.")
            except Exception as e:
                log.error(f"Failed to create role '{role_name}' in guild '{guild.name}': {e}.")

async def setup(bot):
    # Sets up the Color cog.
    try:
        # Attempt to add the Color cog to the bot
        await bot.add_cog(Color(bot))
        log.info("Color cog successfully added to the bot.")
    except Exception as e:
        # Log and handle unexpected errors during setup
        log.error(f"Error setting up Color cog: {e}")