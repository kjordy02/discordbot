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
        log.info("Steam Modul geladen")

    async def get_steamid(self, identifier):
        # Prüfen ob es eine SteamID64 ist
        if identifier.isdigit() and len(identifier) >= 17:
            return identifier

        # Sonst Vanity URL auflösen
        url = f"https://api.steampowered.com/ISteamUser/ResolveVanityURL/v1/?key={STEAM_API_KEY}&vanityurl={identifier}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
                if data["response"]["success"] == 1:
                    return data["response"]["steamid"]
                return None

    @app_commands.command(name="profile", description="Zeigt das Steam Profil eines Spielers.")
    async def steamprofile(self, interaction: discord.Interaction, steamid: str):
        await interaction.response.defer()

        steamid64 = await self.get_steamid(steamid)
        if not steamid64:
            await interaction.followup.send("Steam Profil nicht gefunden.")
            return

        url = f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/?key={STEAM_API_KEY}&steamids={steamid64}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()

        player = data["response"]["players"][0]

        embed = discord.Embed(title=player["personaname"], url=player["profileurl"], color=discord.Color.blue())
        embed.set_thumbnail(url=player["avatarfull"])
        embed.add_field(name="Status", value=player.get("personastate", "Unbekannt"))
        embed.add_field(name="Profil erstellt", value=player.get("timecreated", "Unbekannt"))
        embed.add_field(name="Letzte Anmeldung", value=player.get("lastlogoff", "Unbekannt"))

        await interaction.followup.send(embed=embed)

    @app_commands.command(name="recent", description="Zeigt die zuletzt gespielten Spiele eines Spielers.")
    async def steamrecent(self, interaction: discord.Interaction, steamid: str):
        await interaction.response.defer()

        steamid64 = await self.get_steamid(steamid)
        if not steamid64:
            await interaction.followup.send("Spieler nicht gefunden.")
            return

        url = f"https://api.steampowered.com/IPlayerService/GetRecentlyPlayedGames/v1/?key={STEAM_API_KEY}&steamid={steamid64}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()

        games = data.get("response", {}).get("games", [])

        if not games:
            await interaction.followup.send("Keine Spiele zuletzt gespielt.")
            return

        embed = discord.Embed(title="Zuletzt gespielte Spiele", color=discord.Color.green())
        for game in games:
            embed.add_field(name=game["name"], value=f"Spielzeit: {round(game['playtime_forever'] / 60)} Stunden", inline=False)

        await interaction.followup.send(embed=embed)

    @app_commands.command(name="gametime", description="Zeigt die Spielzeit für ein bestimmtes Spiel eines Spielers.")
    async def steamgame(self, interaction: discord.Interaction, steamid: str, spielname: str):
        await interaction.response.defer()

        steamid64 = await self.get_steamid(steamid)
        if not steamid64:
            await interaction.followup.send("Spieler nicht gefunden.")
            return

        url = f"https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/?key={STEAM_API_KEY}&steamid={steamid64}&include_appinfo=true"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()

        games = data.get("response", {}).get("games", [])
        found = None
        for game in games:
            if spielname.lower() in game["name"].lower():
                found = game
                break

        if not found:
            await interaction.followup.send("Spiel nicht gefunden oder keine Spielzeit vorhanden.")
            return

        hours = round(found["playtime_forever"] / 60)

        embed = discord.Embed(title=found["name"], description=f"Gesamtspielzeit: {hours} Stunden", color=discord.Color.purple())
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="common", description="Zeigt Spiele, die alle angegebenen Steam Accounts besitzen.")
    async def steamcommon(self, interaction: discord.Interaction, steamids: str):
        await interaction.response.defer()

        steamid_list = steamids.split()
        if len(steamid_list) < 2:
            await interaction.followup.send("Bitte gib mindestens zwei Steam-Namen oder IDs an.")
            return

        games_owned = []

        for sid in steamid_list:
            steamid64 = await self.get_steamid(sid)
            if not steamid64:
                await interaction.followup.send(f"Spieler {sid} nicht gefunden oder ungültig.")
                return

            url = f"https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/?key={STEAM_API_KEY}&steamid={steamid64}&include_appinfo=true"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    data = await resp.json()

            games = data.get("response", {}).get("games", [])
            gameset = set(game["name"] for game in games)

            games_owned.append(gameset)

        # Gemeinsame Spiele finden
        common_games = set.intersection(*games_owned)

        if not common_games:
            await interaction.followup.send("Es gibt keine gemeinsamen Spiele.")
            return

        # Embed vorbereiten
        embed = discord.Embed(title="🎮 Gemeinsame Spiele", description="\n".join(sorted(common_games)), color=discord.Color.green())
        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Steam(bot))