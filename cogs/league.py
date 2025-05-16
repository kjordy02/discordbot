import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, button, Button
import aiohttp
import random
import re
from urllib.parse import quote
from logger import get_logger
from config import RIOT_API_KEY

log = get_logger(__name__)

VERSION = "14.9.1"
BASE_URL = f"http://ddragon.leagueoflegends.com/cdn/{VERSION}/data/en_US"
CHAMPION_URL = f"{BASE_URL}/champion.json"

class League(commands.GroupCog, name="lol"):
    """Main class for League of Legends-related commands"""

    def __init__(self, bot):
        self.bot = bot
        self.champion_mapping = None  # Cache for champion ID-to-name mapping

    async def get_champion_mapping(self):
        """Fetches and caches the champion ID-to-name mapping from Riot's API"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(CHAMPION_URL) as resp:
                    if resp.status != 200:
                        log.error(f"Failed to fetch champion mapping. HTTP Status: {resp.status}")
                        return {}
                    data = await resp.json()
                    champions = data['data']
                    log.info("Successfully fetched champion mapping.")
                    return {int(info['key']): name for name, info in champions.items()}
        except Exception as e:
            log.error(f"Error fetching champion mapping: {e}")
            return {}

    @staticmethod
    def parse_riot_id(input_str: str):
        """Parses Riot ID in the format 'GameName#TagLine' and validates it
        Returns (game_name, tag_line) if valid, otherwise None"""
        if "#" not in input_str:
            return None

        parts = input_str.split("#", 1)  # Split at the first #
        game_name = parts[0].strip()
        tag_line = parts[1].strip()

        # Remove non-visible characters and validate lengths
        game_name = re.sub(r'\s+', ' ', game_name)
        tag_line = re.sub(r'\s+', '', tag_line)
        if not (3 <= len(game_name) <= 16 and 2 <= len(tag_line) <= 5):
            return None

        return game_name, tag_line

    @commands.Cog.listener()
    async def on_ready(self):
        """Event listener triggered when the bot is ready"""
        log.info("League module loaded and ready.")

    @app_commands.command(name="stats", description="Shows League of Legends stats based on Riot ID or Summoner Name")
    async def lolstats(self, interaction: discord.Interaction, summoner_name: str):
        """Fetches and displays League of Legends stats for a given Riot ID or Summoner Name"""
        await interaction.response.defer()
        log.info(f"Fetching stats for: {summoner_name}")

        if self.champion_mapping is None:
            # Fetch champion mapping if not already cached
            self.champion_mapping = await self.get_champion_mapping()

        try:
            async with aiohttp.ClientSession() as session:
                parsed = self.parse_riot_id(summoner_name)

                if parsed:
                    # Handle Riot ID format
                    game_name, tag_line = parsed
                    url = f"https://europe.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{quote(game_name)}/{quote(tag_line)}?api_key={RIOT_API_KEY}"
                    async with session.get(url) as resp:
                        if resp.status != 200:
                            log.warning(f"Riot ID not found or invalid. HTTP Status: {resp.status}")
                            await interaction.followup.send("Riot ID not found or invalid.")
                            return
                        account_data = await resp.json()
                        puuid = account_data["puuid"]

                    summoner_url = f"https://euw1.api.riotgames.com/lol/summoner/v4/summoners/by-puuid/{puuid}?api_key={RIOT_API_KEY}"
                else:
                    # Handle Summoner Name format
                    safe_name = quote(summoner_name.strip())
                    summoner_url = f"https://euw1.api.riotgames.com/lol/summoner/v4/summoners/by-name/{safe_name}?api_key={RIOT_API_KEY}"

                async with session.get(summoner_url) as resp:
                    if resp.status != 200:
                        log.warning(f"Summoner not found. HTTP Status: {resp.status}")
                        await interaction.followup.send("Summoner not found.")
                        return
                    summoner_data = await resp.json()

                # Extract summoner details
                summoner_id = summoner_data["id"]
                puuid = summoner_data["puuid"]
                summoner_name = summoner_data.get("name", summoner_name)
                level = summoner_data.get("summonerLevel", "Unknown")

                # Fetch ranked stats
                ranked_url = f"https://euw1.api.riotgames.com/lol/league/v4/entries/by-summoner/{summoner_id}?api_key={RIOT_API_KEY}"
                async with session.get(ranked_url) as resp:
                    ranked_data = await resp.json()

                if ranked_data:
                    ranked_info = ranked_data[0]
                    ranked_text = f"{ranked_info['tier']} {ranked_info['rank']} - {ranked_info['leaguePoints']} LP\nWins: {ranked_info['wins']} | Losses: {ranked_info['losses']}"
                else:
                    ranked_text = "Unranked"

                # Fetch champion mastery score
                mastery_score_url = f"https://euw1.api.riotgames.com/lol/champion-mastery/v4/scores/by-puuid/{puuid}?api_key={RIOT_API_KEY}"
                async with session.get(mastery_score_url) as resp:
                    mastery_score = await resp.json()

                # Fetch top champion mastery
                mastery_url = f"https://euw1.api.riotgames.com/lol/champion-mastery/v4/champion-masteries/by-puuid/{puuid}?api_key={RIOT_API_KEY}"
                async with session.get(mastery_url) as resp:
                    mastery_data = await resp.json()

                top_champions = []
                for champ in mastery_data[:3]:
                    champ_id = champ['championId']
                    champ_points = champ['championPoints']
                    champ_name = self.champion_mapping.get(champ_id, f"Champion {champ_id}")
                    top_champions.append(f"{champ_name}: {champ_points} points")

                # Check live game status
                live_url = f"https://euw1.api.riotgames.com/lol/spectator/v5/active-games/by-summoner/{summoner_id}?api_key={RIOT_API_KEY}"
                async with session.get(live_url) as resp:
                    live_status = "**Currently not in a game.**"
                    if resp.status == 200:
                        live_game = await resp.json()
                        game_mode = live_game.get("gameMode", "Unknown")
                        live_status = f"**Currently in a game → Mode: {game_mode}**"

                # Build and send the embed
                embed = discord.Embed(title=f"{summoner_name} → Level {level}", color=discord.Color.blue())
                embed.add_field(name="Rank", value=ranked_text, inline=False)
                embed.add_field(name="Total Champion Points", value=f"{mastery_score} points", inline=False)
                embed.add_field(name="Top Champions", value="\n".join(top_champions), inline=False)
                embed.add_field(name="Live Status", value=live_status, inline=False)

                await interaction.followup.send(embed=embed)
                log.info(f"Successfully fetched stats for {summoner_name}.")
        except Exception as e:
            # Log and handle unexpected errors
            log.error(f"Error fetching stats for {summoner_name}: {e}")
            await interaction.followup.send("An error occurred while fetching stats. Please try again later.")

    @app_commands.command(name="randomgroups", description="Creates a custom game lobby and generates two random teams.")
    async def randomgroups(self, interaction: discord.Interaction):
        """Creates a custom game lobby and generates two random teams"""
        try:
            view = TeamLobby(interaction.user)
            embed = view.get_lobby_embed()
            await interaction.response.send_message(embed=embed, view=view)
            log.info(f"Custom lobby created by {interaction.user.display_name}.")
        except Exception as e:
            # Log and handle unexpected errors
            log.error(f"Error creating custom lobby: {e}")
            await interaction.response.send_message("An error occurred while creating the lobby. Please try again later.", ephemeral=True)

## VIEWS & BUTTONS

class TeamLobby(View):
    def __init__(self, author: discord.User):
        super().__init__(timeout=300)  # Lobby läuft max. 5 Minuten
        self.players = []
        self.author = author
        self.message = None

    @button(label="Join", style=discord.ButtonStyle.green)
    async def join(self, interaction: discord.Interaction, button: Button):
        user = interaction.user
        if user in self.players:
            await interaction.response.send_message("You already joined!", ephemeral=True)
            return

        self.players.append(user)
        await interaction.response.edit_message(embed=self.get_lobby_embed(), view=self)

    @button(label="Leave", style=discord.ButtonStyle.red)
    async def leave(self, interaction: discord.Interaction, button: Button):
        user = interaction.user
        if user not in self.players:
            await interaction.response.send_message("You are not in the lobby!", ephemeral=True)
            return

        self.players.remove(user)
        await interaction.response.edit_message(embed=self.get_lobby_embed(), view=self)

    @button(label="Generate Teams", style=discord.ButtonStyle.blurple)
    async def generate(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.author:
            await interaction.response.send_message("Only the command initiator can generate teams.", ephemeral=True)
            return

        if len(self.players) < 2:
            await interaction.response.send_message("Need at least 2 players to generate teams.", ephemeral=True)
            return

        team1, team2 = self.split_teams(self.players)
        embed = discord.Embed(title="Teams Generated", color=discord.Color.green())
        embed.add_field(name="Team 1", value="\n".join(p.display_name for p in team1), inline=True)
        embed.add_field(name="Team 2", value="\n".join(p.display_name for p in team2), inline=True)

        for child in self.children:
            child.disabled = True

        await interaction.response.edit_message(embed=embed, view=self)

    def get_lobby_embed(self):
        embed = discord.Embed(title="Custom Lobby", description="Click 'Join' to participate", color=discord.Color.blue())
        if self.players:
            embed.add_field(name="Current Players", value="\n".join(p.display_name for p in self.players), inline=False)
        else:
            embed.add_field(name="Current Players", value="No one yet...", inline=False)
        embed.set_footer(text="Lobby open for 5 minutes")
        return embed

    def split_teams(self, players):
        shuffled = players[:]
        random.shuffle(shuffled)
        mid = len(shuffled) // 2
        return shuffled[:mid], shuffled[mid:]

async def setup(bot):
    """Setup function to add the League cog to the bot"""
    try:
        # Attempt to add the League cog to the bot
        await bot.add_cog(League(bot))
        log.info("League cog successfully added to the bot.")
    except Exception as e:
        # Log and handle unexpected errors during setup
        log.error(f"Error setting up League cog: {e}")