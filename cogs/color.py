import discord
from discord.ext import commands, tasks
from discord import app_commands
import random
from datetime import datetime
from logger import get_logger

log = get_logger(__name__)

class Color(commands.Cog):
    """A cog for managing color roles and automatic color changes for users."""

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
        self.change_colors_hourly.start()

    @commands.Cog.listener()
    async def on_ready(self):
        """Event listener triggered when the bot is ready.
        Ensures that all required color roles exist in all guilds."""
        log.info("Color module loaded and ready.")
        for guild in self.bot.guilds:
            await self.ensure_color_roles(guild)

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        """Event listener triggered when the bot joins a new guild.
        Ensures that all required color roles exist in the new guild."""
        log.info(f"Joined new guild: {guild.name} (ID: {guild.id}). Ensuring color roles.")
        await self.ensure_color_roles(guild)

    @app_commands.command(name="colorchange", description="Toggle automatic color change for yourself.")
    async def colorchange(self, interaction: discord.Interaction):
        """Toggles automatic color changes for the user who invoked the command."""
        guild_id = str(interaction.guild.id)
        user_id = str(interaction.user.id)

        server_db_id = self.bot.db.get_or_create_server(guild_id)
        user_db_id = self.bot.db.get_or_create_user(user_id)

        if self.bot.db.has_color_effect(server_db_id, user_db_id):
            self.bot.db.remove_color_effect(server_db_id, user_db_id)
            await interaction.response.send_message("Color change disabled.", ephemeral=True)
            log.info(f"Disabled color effect for {interaction.user} in {interaction.guild}.")
        else:
            self.bot.db.add_color_effect(server_db_id, user_db_id)
            await interaction.response.send_message("Color change enabled.", ephemeral=True)
            log.info(f"Enabled color effect for {interaction.user} in {interaction.guild}.")

    @tasks.loop(minutes=1)
    async def change_colors_hourly(self):
        """Task that runs every minute to check if it's the start of a new hour.
        If so, rotates the colors for users who have enabled automatic color changes."""
        now = datetime.now()
        if now.minute != 0:
            return  # Only run at the start of each hour

        log.info(f"Starting color rotation for hour {now.hour}.")

        for guild in self.bot.guilds:
            try:
                server_db_id = self.bot.db.get_or_create_server(guild.id)
                affected_users = self.bot.db.get_color_effect_users(server_db_id)
                await self.rotate_colors(guild, affected_users)
            except Exception as e:
                log.error(f"Color rotation failed for guild {guild.id}: {e}")
        
    async def rotate_colors(self, guild, user_ids):
        for member in guild.members:
            if member.bot or member.id not in user_ids:
                continue

            current_roles = [r.name for r in member.roles if r.name in self.color_roles]
            current = current_roles[0] if current_roles else None
            possible_colors = [c for c in self.color_roles if c != current]
            new_color = random.choice(possible_colors)
            new_role = discord.utils.get(guild.roles, name=new_color)

            if not new_role:
                continue

            try:
                await member.remove_roles(*[r for r in member.roles if r.name in self.color_roles])
                await member.add_roles(new_role)
                log.info(f"Updated {member.display_name} to {new_color} in {guild.name}")
            except Exception as e:
                log.warning(f"Failed to update color for {member.id} in {guild.name}: {e}")


    @change_colors_hourly.before_loop
    async def before(self):
        """Waits until the bot is ready before starting the color rotation task."""
        log.info("Waiting for bot to be ready before starting color rotation task.")
        await self.bot.wait_until_ready()

    async def ensure_color_roles(self, guild: discord.Guild):
        """Ensures that all required color roles exist in the specified guild.
        If a role is missing, it is created and positioned just below the bot's top role."""
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
    """Sets up the Color cog."""
    try:
        # Attempt to add the Color cog to the bot
        await bot.add_cog(Color(bot))
        log.info("Color cog successfully added to the bot.")
    except Exception as e:
        # Log and handle unexpected errors during setup
        log.error(f"Error setting up Color cog: {e}")