import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import random
from logger import get_logger

log = get_logger(__name__)

VERSION = "14.9.1"
BASE_URL = f"http://ddragon.leagueoflegends.com/cdn/{VERSION}/data/en_US"
CHAMPION_URL = f"{BASE_URL}/champion.json"
ITEM_URL = f"{BASE_URL}/item.json"
SUMMONER_SPELL_URL = f"{BASE_URL}/summoner.json"
RUNES_URL = f"{BASE_URL}/runesReforged.json"

ROLES = ["TOP", "JUNGLE", "MID", "ADC", "SUPPORT"]
STARTER_ITEMS = ["Doran's Blade", "Doran's Ring", "Doran's Shield", "Cull", "Tear of the Goddess", "Corrupting Potion", "Dark Seal", "Long Sword", "Amplifying Tome", "Cloth Armor", "Sapphire Crystal"]
SUPPORT_UPGRADES = [
    "Celestial Opposition",
    "Solstice Sleigh",
    "Bloodsong",
    "Dream Maker",
    "Zaz’Zak’s Realmspike"
]
JUNGLE_ITEMS = {
    "Mosstomper Seedling": "Mosstomper",
    "Scorchclaw Pup": "Scorchclaw",
    "Gustwalker Hatchling": "Gustwalker"
}

# Ornn Masterwork Items (should be excluded from Ultimate Bravery)
MASTERWORK_ITEMS = {
    "Forgefire Crest",
    "Rimeforged Grasp",
    "Molten Edge",
    "Liandry's Lament",
    "Rabadon's Deathcrown",
    "Infinity Force",
    "Syzygy",
    "Dreamshatter",
    "Shurelya's Requiem",
    "Cry of the Shrieking City",
    "Reliquary of the Golden Dawn",
    "Upgraded Aeropack",
    "The Unspoken Parasite",
    "Starcaster",
    "Vespertide",
    "Bloodward",
    "Obsidian Cleaver",
    "Ceaseless Hunger",
    "Typhoon",
    "Deicide",
    "Edge of Finality",
    "Flicker",
    "Heavensfall",
    "Icathia's Curse",
    "Leviathan",
    "Might of the Ruined King",
    "Sandshrike's Claw",
    "Seat of Command",
    "Shojin's Resolve",
    "The Baron's Gift",
    "Wyrmfallen Sacrifice"
}

class UltimateBravery(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.events = {}

    @commands.Cog.listener()
    async def on_ready(self):
        log.info("Ultimate Bravery module loaded")

    async def fetch_json(self, session, url):
        async with session.get(url) as response:
            return await response.json()

    @app_commands.command(name="ultimatebravery", description="Start an Ultimate Bravery event")
    @app_commands.describe(spielmodus="Choose the game mode")
    @app_commands.choices(spielmodus=[
        app_commands.Choice(name="Summoner's Rift", value="sr"),
        app_commands.Choice(name="ARAM", value="aram")
    ])
    async def ultimatebravery(self, interaction: discord.Interaction, spielmodus: app_commands.Choice[str]):
        await interaction.response.send_message("Ultimate Bravery started! Click **Join** to participate.", view=JoinView(self, interaction.user.id, spielmodus.value))

    async def generate_build(self, user, mode, taken_champions, taken_roles):
        async with aiohttp.ClientSession() as session:
            champions_data = await self.fetch_json(session, CHAMPION_URL)
            items_data = await self.fetch_json(session, ITEM_URL)
            spells_data = await self.fetch_json(session, SUMMONER_SPELL_URL)
            runes_data = await self.fetch_json(session, RUNES_URL)

        champions = [c for c in champions_data["data"].keys() if c not in taken_champions]
        champion = random.choice(champions)
        taken_champions.append(champion)

        role = None
        if mode == "sr":
            roles = [r for r in ROLES if r not in taken_roles]
            role = random.choice(roles)
            taken_roles.append(role)

        valid_spells = [s["name"] for s in spells_data["data"].values() if (mode == "sr" and "CLASSIC" in s["modes"]) or (mode == "aram" and "ARAM" in s["modes"])]
        spell1 = random.choice(valid_spells)
        spell2 = random.choice([s for s in valid_spells if s != spell1])
        if mode == "sr" and role == "JUNGLE":
            spell1 = "Smite"
            spell2 = random.choice([s for s in valid_spells if s != "Smite"])

        boots = [
            i["name"] for i in items_data["data"].values()
            if "Boots" in i.get("tags", [])
            and i.get("maps", {}).get("11", False)
            and i["name"] != "Slightly Magical Boots"
        ]
        full_items = [
            i["name"] for i in items_data["data"].values()
            if i.get("gold", {}).get("total", 0) >= 2000 and i.get("maps", {}).get("11", False) and i["name"] not in MASTERWORK_ITEMS
        ]
        build_items = [random.choice(boots)] + random.sample(full_items, 5)

        primary_path = random.choice(runes_data)
        primary_keystone = random.choice(primary_path["slots"][0]["runes"])
        primary_runes = [random.choice(slot["runes"]) for slot in primary_path["slots"][1:]]

        secondary_paths = [p for p in runes_data if p["id"] != primary_path["id"]]
        secondary_path = random.choice(secondary_paths)
        secondary_runes_pool = [r for slot in secondary_path["slots"][1:] for r in slot["runes"]]
        secondary_runes = random.sample(secondary_runes_pool, 2)

        if role == "SUPPORT":
            starter = f"World Atlas → {random.choice(SUPPORT_UPGRADES)}"
        elif role == "JUNGLE":
            jungle_choice = random.choice(list(JUNGLE_ITEMS.items()))
            starter = f"{jungle_choice[0]} → {jungle_choice[1]}"
        else:
            starter = random.choice(STARTER_ITEMS)

        first_skill = random.choice(["Q", "W", "E"])

        embed = discord.Embed(title=f"🎲 Ultimate Bravery for {user.display_name}", color=discord.Color.gold())
        embed.add_field(name="Role & Champion", value=f"{role or '-'} → **{champion}**", inline=False)
        embed.add_field(name="Summoner Spells & First Max", value=f"{spell1} + {spell2} → First Max: {first_skill}", inline=False)
        embed.add_field(name="Runes", value=f"**{primary_path['name']}**: {primary_keystone['name']}, {', '.join(r['name'] for r in primary_runes)}\n**{secondary_path['name']}**: {', '.join(r['name'] for r in secondary_runes)}", inline=False)
        embed.add_field(name="Starter & Items", value=f"Starter: {starter}\n" + "\n".join(f"- {item}" for item in build_items), inline=False)

        return embed, champion, role

class JoinView(discord.ui.View):
    def __init__(self, cog, host_id, mode):
        super().__init__(timeout=None)
        self.cog = cog
        self.host_id = host_id
        self.mode = mode
        self.players = []

    @discord.ui.button(label="Join", style=discord.ButtonStyle.green)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in [u.id for u in self.players]:
            self.players.append(interaction.user)
            await interaction.response.edit_message(content=f"Ultimate Bravery started! Participants: {', '.join([u.display_name for u in self.players])}", view=self)
        else:
            await interaction.response.send_message("You have already joined!", ephemeral=True)

    @discord.ui.button(label="Generate Builds", style=discord.ButtonStyle.blurple)
    async def generate(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.host_id:
            await interaction.response.send_message("Only the host can generate builds!", ephemeral=True)
            return

        if not self.players:
            await interaction.response.send_message("No players in the lobby!", ephemeral=True)
            return

        taken_champs = []
        taken_roles = []
        for player in self.players:
            embed, champ, role = await self.cog.generate_build(player, self.mode, taken_champs, taken_roles)
            await interaction.channel.send(content=player.mention, embed=embed, view=RerollView(self.cog, player, self.mode, taken_champs.copy(), taken_roles.copy()))

        for child in self.children:
            child.disabled = True

        await interaction.message.edit(content="❗ **Lobby closed. Builds have been generated.**", view=self)

class RerollView(discord.ui.View):
    def __init__(self, cog, player, mode, taken_champs, taken_roles):
        super().__init__(timeout=900)
        self.cog = cog
        self.player = player
        self.mode = mode
        self.taken_champs = taken_champs
        self.taken_roles = taken_roles

    @discord.ui.button(label="Reroll my Build", style=discord.ButtonStyle.red)
    async def reroll(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.player:
            await interaction.response.send_message("You can only reroll your own build!", ephemeral=True)
            return

        embed, champ, role = await self.cog.generate_build(self.player, self.mode, self.taken_champs, self.taken_roles)
        await interaction.response.edit_message(embed=embed)

async def setup(bot):
    await bot.add_cog(UltimateBravery(bot))