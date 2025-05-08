import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
from logger import get_logger
from config import STEAM_API_KEY

log = get_logger(__name__)

class Steam(commands.GroupCog, name="steam"):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        log.info("Steam module loaded")

    async def get_steamid(self, identifier):
        # Check if it's a SteamID64
        if identifier.isdigit() and len(identifier) >= 17:
            return identifier

        # Otherwise resolve vanity URL
        url = f"https://api.steampowered.com/ISteamUser/ResolveVanityURL/v1/?key={STEAM_API_KEY}&vanityurl={identifier}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
                if data["response"]["success"] == 1:
                    return data["response"]["steamid"]
                return None

    @app_commands.command(name="profile", description="Shows the Steam profile of a player.")
    async def steamprofile(self, interaction: discord.Interaction, steamid: str):
        await interaction.response.defer()

        steamid64 = await self.get_steamid(steamid)
        if not steamid64:
            await interaction.followup.send("Steam profile not found.")
            return

        url = f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/?key={STEAM_API_KEY}&steamids={steamid64}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()

        player = data["response"]["players"][0]

        embed = discord.Embed(title=player["personaname"], url=player["profileurl"], color=discord.Color.blue())
        embed.set_thumbnail(url=player["avatarfull"])
        embed.add_field(name="Status", value=player.get("personastate", "Unknown"))
        embed.add_field(name="Account Created", value=player.get("timecreated", "Unknown"))
        embed.add_field(name="Last Logoff", value=player.get("lastlogoff", "Unknown"))

        await interaction.followup.send(embed=embed)

    @app_commands.command(name="recent", description="Shows the most recently played games of a player.")
    async def steamrecent(self, interaction: discord.Interaction, steamid: str):
        await interaction.response.defer()

        steamid64 = await self.get_steamid(steamid)
        if not steamid64:
            await interaction.followup.send("Player not found.")
            return

        url = f"https://api.steampowered.com/IPlayerService/GetRecentlyPlayedGames/v1/?key={STEAM_API_KEY}&steamid={steamid64}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()

        games = data.get("response", {}).get("games", [])

        if not games:
            await interaction.followup.send("No recently played games found.")
            return

        embed = discord.Embed(title="Recently Played Games", color=discord.Color.green())
        for game in games:
            embed.add_field(name=game["name"], value=f"Playtime: {round(game['playtime_forever'] / 60)} hours", inline=False)

        await interaction.followup.send(embed=embed)

    @app_commands.command(name="gametime", description="Shows the total playtime for a specific game.")
    async def steamgame(self, interaction: discord.Interaction, steamid: str, game_name: str):
        await interaction.response.defer()

        steamid64 = await self.get_steamid(steamid)
        if not steamid64:
            await interaction.followup.send("Player not found.")
            return

        url = f"https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/?key={STEAM_API_KEY}&steamid={steamid64}&include_appinfo=true"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()

        games = data.get("response", {}).get("games", [])
        found = None
        for game in games:
            if game_name.lower() in game["name"].lower():
                found = game
                break

        if not found:
            await interaction.followup.send("Game not found or no playtime recorded.")
            return

        hours = round(found["playtime_forever"] / 60)
        embed = discord.Embed(title=found["name"], description=f"Total playtime: {hours} hours", color=discord.Color.purple())
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="common", description="Shows games that all given Steam accounts have in common.")
    async def steamcommon(self, interaction: discord.Interaction, steamids: str):
        await interaction.response.defer()

        steamid_list = steamids.split()
        if len(steamid_list) < 2:
            await interaction.followup.send("Please provide at least two Steam names or IDs.")
            return

        games_owned = []

        for sid in steamid_list:
            steamid64 = await self.get_steamid(sid)
            if not steamid64:
                await interaction.followup.send(f"Player {sid} not found or invalid.")
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
    await bot.add_cog(Steam(bot))