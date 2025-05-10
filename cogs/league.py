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
    def __init__(self, bot):
        self.bot = bot
        self.champion_mapping = None

    async def get_champion_mapping(self):
        async with aiohttp.ClientSession() as session:
            async with session.get(CHAMPION_URL) as resp:
                data = await resp.json()
                champions = data['data']
                return {int(info['key']): name for name, info in champions.items()}
    

    @staticmethod
    def parse_riot_id(input_str: str):
        """
        Parses Riot ID in the format 'GameName#TagLine' and returns (game_name, tag_line).
        Handles edge cases: extra spaces, multiple #, weird characters.

        Returns:
            (game_name, tag_line) if valid, otherwise None
        """

        if "#" not in input_str:
            return None

        # Split only at the FIRST #, in case there are multiple
        parts = input_str.split("#", 1)
        game_name = parts[0].strip()
        tag_line = parts[1].strip()

        # Remove non-visible / invisible unicode characters (zero width spaces, etc)
        game_name = re.sub(r'\s+', ' ', game_name)  # collapse multiple spaces
        tag_line = re.sub(r'\s+', '', tag_line)     # taglines never have spaces

        # Validate → Riot allows at least 3 chars GameName + 2 chars Tagline, max 16 and 5
        if not (3 <= len(game_name) <= 16 and 2 <= len(tag_line) <= 5):
            return None

        return game_name, tag_line

    @commands.Cog.listener()
    async def on_ready(self):
        log.info("League module loaded")

    @app_commands.command(name="stats", description="Shows League of Legends stats based on Riot ID or Summoner Name")
    async def lolstats(self, interaction: discord.Interaction, summoner_name: str):
        await interaction.response.defer()

        if self.champion_mapping is None:
            self.champion_mapping = await self.get_champion_mapping()

        async with aiohttp.ClientSession() as session:

            parsed = self.parse_riot_id(summoner_name)

            if parsed:
                game_name, tag_line = parsed

                url = f"https://europe.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{quote(game_name)}/{quote(tag_line)}?api_key={RIOT_API_KEY}"
                async with session.get(url) as resp:
                    log.warning(resp.status_code)
                    if resp.status != 200:
                        await interaction.followup.send("Riot ID not found or invalid.")
                        return
                    account_data = await resp.json()
                    puuid = account_data["puuid"]

                summoner_url = f"https://euw1.api.riotgames.com/lol/summoner/v4/summoners/by-puuid/{puuid}?api_key={RIOT_API_KEY}"

            else:
                safe_name = quote(summoner_name.strip())
                summoner_url = f"https://euw1.api.riotgames.com/lol/summoner/v4/summoners/by-name/{safe_name}?api_key={RIOT_API_KEY}"
            
            async with session.get(summoner_url) as resp:
                if resp.status != 200:
                    await interaction.followup.send("Summoner not found.")
                    return
                summoner_data = await resp.json()

            summoner_id = summoner_data["id"]
            puuid = summoner_data["puuid"]
            summoner_name = summoner_data.get("name", summoner_name)
            level = summoner_data.get("summonerLevel", "Unknown")

            ranked_url = f"https://euw1.api.riotgames.com/lol/league/v4/entries/by-summoner/{summoner_id}?api_key={RIOT_API_KEY}"
            async with session.get(ranked_url) as resp:
                ranked_data = await resp.json()

            if ranked_data:
                ranked_info = ranked_data[0]
                ranked_text = f"{ranked_info['tier']} {ranked_info['rank']} - {ranked_info['leaguePoints']} LP\nWins: {ranked_info['wins']} | Losses: {ranked_info['losses']}"
            else:
                ranked_text = "Unranked"

            mastery_score_url = f"https://euw1.api.riotgames.com/lol/champion-mastery/v4/scores/by-puuid/{puuid}?api_key={RIOT_API_KEY}"
            async with session.get(mastery_score_url) as resp:
                mastery_score = await resp.json()

            mastery_url = f"https://euw1.api.riotgames.com/lol/champion-mastery/v4/champion-masteries/by-puuid/{puuid}?api_key={RIOT_API_KEY}"
            async with session.get(mastery_url) as resp:
                mastery_data = await resp.json()

            top_champions = []
            for champ in mastery_data[:3]:
                champ_id = champ['championId']
                champ_points = champ['championPoints']
                champ_name = self.champion_mapping.get(champ_id, f"Champion {champ_id}")
                top_champions.append(f"{champ_name}: {champ_points} points")

            live_url = f"https://euw1.api.riotgames.com/lol/spectator/v5/active-games/by-summoner/{summoner_id}?api_key={RIOT_API_KEY}"
            async with session.get(live_url) as resp:
                live_status = "**Currently not in a game.**"
                if resp.status == 200:
                    live_game = await resp.json()
                    game_mode = live_game.get("gameMode", "Unknown")
                    live_status = f"**Currently in a game → Mode: {game_mode}**"

            embed = discord.Embed(title=f"{summoner_name} → Level {level}", color=discord.Color.blue())
            embed.add_field(name="Rank", value=ranked_text, inline=False)
            embed.add_field(name="Total Champion Points", value=f"{mastery_score} points", inline=False)
            embed.add_field(name="Top Champions", value="\n".join(top_champions), inline=False)
            embed.add_field(name="Live Status", value=live_status, inline=False)

            await interaction.followup.send(embed=embed)

    @app_commands.command(name="randomgroups", description="Creates a custom game lobby and generates two random teams.")
    async def randomgroups(self, interaction: discord.Interaction):
        view = TeamLobby(interaction.user)
        embed = view.get_lobby_embed()
        await interaction.response.send_message(embed=embed, view=view)

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
    await bot.add_cog(League(bot))