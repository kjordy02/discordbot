import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import re
from difflib import get_close_matches
from logger import get_logger
from config import STEAM_API_KEY

log = get_logger(__name__)

class Steam(commands.GroupCog, name="steam"):
    """Main class for Steam-related commands."""

    def __init__(self, bot):
        """Initializes the Steam cog with the bot instance."""
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        """Event listener triggered when the bot is ready."""
        log.info("Steam module loaded and ready.")

    async def get_steamid(self, identifier):
        """Resolves a Steam identifier (SteamID64, profile URL, or vanity URL) to a SteamID64."""
        try:
            # Check if the identifier is a valid SteamID64
            if identifier.isdigit() and len(identifier) >= 17:
                return identifier

            # Check if the identifier is a profile URL and extract the ID or vanity
            url_pattern = r"(?:https?://)?steamcommunity\.com/(id|profiles)/([^/]+)/?"
            match = re.match(url_pattern, identifier)
            if match:
                identifier = match.group(2)
                if match.group(1) == "profiles" and identifier.isdigit():
                    return identifier  # It's already a SteamID64

            # Try resolving the identifier as a vanity URL
            url = f"https://api.steampowered.com/ISteamUser/ResolveVanityURL/v1/?key={STEAM_API_KEY}&vanityurl={identifier}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        log.warning(f"Failed to resolve vanity URL. HTTP Status: {resp.status}")
                        return None
                    data = await resp.json()
                    if data["response"]["success"] == 1:
                        log.info(f"Successfully resolved vanity URL to SteamID64: {data['response']['steamid']}")
                        return data["response"]["steamid"]

            # Could not resolve the identifier
            log.warning(f"Could not resolve identifier: {identifier}")
            return None
        except Exception as e:
            # Log and handle unexpected errors
            log.error(f"Error resolving Steam identifier: {e}")
            return None

    async def send_invalid_identifier(self, interaction: discord.Interaction, identifier: str):
        """Sends an error message for invalid Steam identifiers."""
        try:
            # Send a public error message
            await interaction.followup.send(f"❗ Steam profile for `{identifier}` not found.", ephemeral=False)

            # Send an ephemeral help guide
            guide = (
                "ℹ️ **Why this happened:**\n"
                "- You might not have set a **Custom URL (Vanity URL)** in your Steam profile.\n"
                "- You may have used your **Steam display name**, which is not supported.\n\n"
                "**Supported identifiers:**\n"
                "✅ SteamID64 (17-digit numeric ID)\n"
                "✅ Profile URL (https://steamcommunity.com/profiles/...) or Vanity URL (https://steamcommunity.com/id/...)\n\n"
                "**How to set your Custom URL:**\n"
                "1. Open your Steam profile in your browser or Steam client.\n"
                "2. Click 'Edit Profile'.\n"
                "3. Set your 'Custom URL'.\n"
                "4. Use `/steam profile <yourCustomURL>` in Discord."
            )
            await interaction.followup.send(guide, ephemeral=True)
            log.info(f"Sent invalid identifier message for: {identifier}")
        except Exception as e:
            # Log and handle unexpected errors
            log.error(f"Error sending invalid identifier message: {e}")
    
    @staticmethod
    def find_best_match(games, user_input):
        """Finds the best matching game from a list of games based on user input."""
        user_input = re.sub(r'\W+', '', user_input).lower()
        exact = []
        starts = []
        contains = []

        for game in games:
            raw_name = game.get("name", "")
            normalized_name = re.sub(r'\W+', '', raw_name).lower()

            if normalized_name == user_input:
                exact.append(game)
            elif normalized_name.startswith(user_input):
                starts.append(game)
            elif user_input in normalized_name:
                contains.append(game)

        if exact:
            return exact[0]
        if starts:
            return starts[0]
        if contains:
            from difflib import get_close_matches
            norm_names = [re.sub(r'\W+', '', g["name"]).lower() for g in contains]
            matches = get_close_matches(user_input, norm_names, n=1, cutoff=0.0)
            if matches:
                for g in contains:
                    if re.sub(r'\W+', '', g["name"]).lower() == matches[0]:
                        return g
            contains.sort(key=lambda g: g.get("playtime_forever", 0), reverse=True)
            return contains[0]

        return None

    @app_commands.command(name="profile", description="Shows the Steam profile of a player.")
    async def steamprofile(self, interaction: discord.Interaction, steamid: str):
        """Fetches and displays the Steam profile of a player."""
        await interaction.response.defer()
        log.info(f"Fetching profile for: {steamid}")

        try:
            steamid64 = await self.get_steamid(steamid)
            if not steamid64:
                await self.send_invalid_identifier(interaction, steamid)
                return

            url = f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/?key={STEAM_API_KEY}&steamids={steamid64}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        log.warning(f"Failed to fetch profile. HTTP Status: {resp.status}")
                        await interaction.followup.send("Failed to fetch Steam profile.")
                        return
                    data = await resp.json()

            player = data["response"]["players"][0]
            embed = discord.Embed(title=player["personaname"], url=player["profileurl"], color=discord.Color.blue())
            embed.set_thumbnail(url=player["avatarfull"])

            # Add account status and creation time
            status = player.get("personastate", "Unknown")
            embed.add_field(name="Status", value=status)

            time_created = player.get("timecreated")
            if time_created:
                created_at = f"<t:{time_created}:f> (<t:{time_created}:R>)"
            else:
                created_at = "Unknown"
            embed.add_field(name="Account Created", value=created_at)

            last_logoff = player.get("lastlogoff")
            if last_logoff:
                logoff_at = f"<t:{last_logoff}:f> (<t:{last_logoff}:R>)"
            else:
                logoff_at = "Unknown"
            embed.add_field(name="Last Logoff", value=logoff_at)

            await interaction.followup.send(embed=embed)
            log.info(f"Successfully fetched profile for: {steamid}")
        except Exception as e:
            # Log and handle unexpected errors
            log.error(f"Error fetching profile for {steamid}: {e}")
            await interaction.followup.send("An error occurred while fetching the profile. Please try again later.")

    @app_commands.command(name="recent", description="Shows the most recently played games of a player.")
    async def steamrecent(self, interaction: discord.Interaction, steamid: str):
        """Fetches and displays the most recently played games of a player."""
        await interaction.response.defer()
        log.info(f"Fetching recent games for: {steamid}")

        try:
            steamid64 = await self.get_steamid(steamid)
            if not steamid64:
                await self.send_invalid_identifier(interaction, steamid)
                return

            url = f"https://api.steampowered.com/IPlayerService/GetRecentlyPlayedGames/v1/?key={STEAM_API_KEY}&steamid={steamid64}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        log.warning(f"Failed to fetch recent games. HTTP Status: {resp.status}")
                        await interaction.followup.send("Failed to fetch recently played games.")
                        return
                    data = await resp.json()

            games = data.get("response", {}).get("games", [])

            if not games:
                await interaction.followup.send("No recently played games found.")
                return

            embed = discord.Embed(title="Recently Played Games", color=discord.Color.green())
            for game in games:
                embed.add_field(name=game["name"], value=f"Playtime: {round(game['playtime_forever'] / 60)} hours", inline=False)

            await interaction.followup.send(embed=embed)
            log.info(f"Successfully fetched recent games for: {steamid}")
        except Exception as e:
            # Log and handle unexpected errors
            log.error(f"Error fetching recent games for {steamid}: {e}")
            await interaction.followup.send("An error occurred while fetching recent games. Please try again later.")

    @app_commands.command(name="gametime", description="Shows the total playtime for a specific game.")
    async def steamgame(self, interaction: discord.Interaction, steamid: str, game_name: str):
        """Fetches and displays the total playtime for a specific game."""
        await interaction.response.defer()

        steamid64 = await self.get_steamid(steamid)
        if not steamid64:
            await self.send_invalid_identifier(interaction, steamid)
            return

        url = f"https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/?key={STEAM_API_KEY}&steamid={steamid64}&include_appinfo=true"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()

        games = data.get("response", {}).get("games", [])
        found = self.find_best_match(games, game_name)

        if not found:
            await interaction.followup.send("Game not found or no playtime recorded.")
            return

        hours_total = round(found["playtime_forever"] / 60)
        hours_recent = round(found.get("playtime_2weeks", 0) / 60)

        embed = discord.Embed(
            title=found["name"],
            description=f"🎮 Total playtime: **{hours_total} hours**\n🕒 Last 2 weeks: **{hours_recent} hours**",
            color=discord.Color.purple()
        )

       # img_logo_url is NOT always present or not valid
        logo_hash = found.get("img_logo_url")
        appid = found.get("appid")

        if logo_hash:
            logo_url = f"https://media.steampowered.com/steamcommunity/public/images/apps/{appid}/{logo_hash}.jpg"
            embed.set_thumbnail(url=logo_url)

        # Optional: Steam Stats
        if found.get("has_community_visible_stats"):
            stats_url = f"https://steamcommunity.com/stats/{appid}/achievements/"
            embed.add_field(name="🔗 Steam Stats", value=f"[View Achievements]({stats_url})", inline=False)
        
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="common", description="Shows games that all given Steam accounts have in common.")
    async def steamcommon(self, interaction: discord.Interaction, steamids: str):
        """Fetches and displays games that all given Steam accounts have in common."""
        await interaction.response.defer()

        steamid_list = steamids.split()
        if len(steamid_list) < 2:
            await interaction.followup.send("Please provide at least two Steam names or IDs.")
            return

        games_owned = []

        for sid in steamid_list:
            steamid64 = await self.get_steamid(sid)
            if not steamid64:
                await self.send_invalid_identifier(interaction, sid)
                return

            url = f"https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/?key={STEAM_API_KEY}&steamid={steamid64}&include_appinfo=true"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    data = await resp.json()

            games = data.get("response", {}).get("games", [])
            gameset = set(game["name"] for game in games)
            games_owned.append(gameset)

        common_games = set.intersection(*games_owned)

        if not common_games:
            await interaction.followup.send("No common games found.")
            return

        embed = discord.Embed(title="🎮 Common Games", description="\n".join(sorted(common_games)), color=discord.Color.green())
        await interaction.followup.send(embed=embed)

async def setup(bot):
    """Sets up the Steam cog."""
    try:
        # Attempt to add the Steam cog to the bot
        await bot.add_cog(Steam(bot))
        log.info("Steam cog successfully added to the bot.")
    except Exception as e:
        # Log and handle unexpected errors during setup
        log.error(f"Error setting up Steam cog: {e}")