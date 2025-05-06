import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
from urllib.parse import quote

VERSION = "14.9.1"
RIOT_API_KEY = "RGAPI-9e84f730-250c-4f09-86ad-37d53961a285"
BASE_URL = f"http://ddragon.leagueoflegends.com/cdn/{VERSION}/data/en_US"
CHAMPION_URL = f"{BASE_URL}/champion.json"

class League(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.champion_mapping = None

    async def get_champion_mapping(self):
        async with aiohttp.ClientSession() as session:
            async with session.get(CHAMPION_URL) as resp:
                data = await resp.json()
                champions = data['data']
                return {int(info['key']): name for name, info in champions.items()}

    @commands.Cog.listener()
    async def on_ready(self):
        print("League Modul geladen")

    @app_commands.command(name="lolstats", description="Zeigt League of Legends Stats anhand von Riot ID oder Summoner Name")
    async def lolstats(self, interaction: discord.Interaction, summoner_name: str):
        await interaction.response.defer()

        if self.champion_mapping is None:
            self.champion_mapping = await self.get_champion_mapping()

        async with aiohttp.ClientSession() as session:
            if "#" in summoner_name:
                try:
                    game_name, tag_line = summoner_name.split("#")
                except ValueError:
                    await interaction.followup.send("Ungültiges Format. Nutze z.B. Jordy#EUW.")
                    return

                url = f"https://europe.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{quote(game_name)}/{quote(tag_line)}?api_key={RIOT_API_KEY}"
                async with session.get(url) as resp:
                    if resp.status != 200:
                        await interaction.followup.send("Riot ID nicht gefunden oder ungültig.")
                        return
                    account_data = await resp.json()
                    puuid = account_data["puuid"]

                summoner_url = f"https://euw1.api.riotgames.com/lol/summoner/v4/summoners/by-puuid/{puuid}?api_key={RIOT_API_KEY}"
            else:
                safe_name = quote(summoner_name)
                summoner_url = f"https://euw1.api.riotgames.com/lol/summoner/v4/summoners/by-name/{safe_name}?api_key={RIOT_API_KEY}"

            async with session.get(summoner_url) as resp:
                if resp.status != 200:
                    await interaction.followup.send("Summoner nicht gefunden.")
                    return
                summoner_data = await resp.json()

            summoner_id = summoner_data["id"]
            puuid = summoner_data["puuid"]
            summoner_name = summoner_data.get("name", summoner_name)
            level = summoner_data.get("summonerLevel", "Unbekannt")

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
                top_champions.append(f"{champ_name}: {champ_points} Punkte")

            live_url = f"https://euw1.api.riotgames.com/lol/spectator/v5/active-games/by-summoner/{summoner_id}?api_key={RIOT_API_KEY}"
            async with session.get(live_url) as resp:
                live_status = "**Aktuell nicht im Spiel.**"
                if resp.status == 200:
                    live_game = await resp.json()
                    game_mode = live_game.get("gameMode", "Unbekannt")
                    live_status = f"**Aktuell im Spiel → Modus: {game_mode}**"

            embed = discord.Embed(title=f"{summoner_name} → Level {level}", color=discord.Color.blue())
            embed.add_field(name="Rang", value=ranked_text, inline=False)
            embed.add_field(name="Champion Punkte Gesamt", value=f"{mastery_score} Punkte", inline=False)
            embed.add_field(name="Top Champions", value="\n".join(top_champions), inline=False)
            embed.add_field(name="Live Status", value=live_status, inline=False)

            await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(League(bot))