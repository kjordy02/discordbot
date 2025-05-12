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

class UltimateBravery(commands.GroupCog, name="lol"):
    # Main class for the Ultimate Bravery game cog
    def __init__(self, bot):
        self.bot = bot
        self.events = {}

    @commands.Cog.listener()
    async def on_ready(self):
        # Event listener triggered when the bot is ready
        log.info("Ultimate Bravery module loaded and ready.")

    async def fetch_json(self, session, url):
        # Fetches JSON data from a given URL
        try:
            async with session.get(url) as response:
                if response.status != 200:
                    log.warning(f"Failed to fetch data from {url}. HTTP Status: {response.status}")
                    return {}
                return await response.json()
        except Exception as e:
            # Log and handle unexpected errors
            log.error(f"Error fetching data from {url}: {e}")
            return {}

    @app_commands.command(name="ultimatebravery", description="Start an Ultimate Bravery event")
    @app_commands.describe(spielmodus="Choose the game mode")
    @app_commands.choices(spielmodus=[
        app_commands.Choice(name="Summoner's Rift", value="sr"),
        app_commands.Choice(name="ARAM", value="aram")
    ])
    async def ultimatebravery(self, interaction: discord.Interaction, spielmodus: app_commands.Choice[str]):
        # Starts an Ultimate Bravery event
        try:
            await interaction.response.send_message("Ultimate Bravery started! Click **Join** to participate.", view=JoinView(self, interaction.user.id, spielmodus.value))
            log.info(f"Ultimate Bravery event started by {interaction.user.display_name}.")
        except Exception as e:
            # Log and handle unexpected errors
            log.error(f"Error starting Ultimate Bravery event: {e}")
            await interaction.response.send_message("An error occurred while starting the event. Please try again later.", ephemeral=True)

    async def generate_build(self, user, mode, taken_champions, taken_roles):
        # Generates a random build for a player
        try:
            async with aiohttp.ClientSession() as session:
                champions_data = await self.fetch_json(session, CHAMPION_URL)
                items_data = await self.fetch_json(session, ITEM_URL)
                spells_data = await self.fetch_json(session, SUMMONER_SPELL_URL)
                runes_data = await self.fetch_json(session, RUNES_URL)

            # Select a random champion
            champions = [c for c in champions_data["data"].keys() if c not in taken_champions]
            champion = random.choice(champions)
            taken_champions.append(champion)

            # Assign a role if the mode is Summoner's Rift
            role = None
            if mode == "sr":
                roles = [r for r in ROLES if r not in taken_roles]
                role = random.choice(roles)
                taken_roles.append(role)

            # Select summoner spells
            valid_spells = [s["name"] for s in spells_data["data"].values() if (mode == "sr" and "CLASSIC" in s["modes"]) or (mode == "aram" and "ARAM" in s["modes"])]
            spell1 = random.choice(valid_spells)
            spell2 = random.choice([s for s in valid_spells if s != spell1])
            if mode == "sr" and role == "JUNGLE":
                spell1 = "Smite"
                spell2 = random.choice([s for s in valid_spells if s != "Smite"])

            # Select items
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

            # Select runes
            primary_path = random.choice(runes_data)
            primary_keystone = random.choice(primary_path["slots"][0]["runes"])
            primary_runes = [random.choice(slot["runes"]) for slot in primary_path["slots"][1:]]

            secondary_paths = [p for p in runes_data if p["id"] != primary_path["id"]]
            secondary_path = random.choice(secondary_paths)
            secondary_runes_pool = [r for slot in secondary_path["slots"][1:] for r in slot["runes"]]
            secondary_runes = random.sample(secondary_runes_pool, 2)

            # Select starter items
            if role == "SUPPORT":
                starter = f"World Atlas → {random.choice(SUPPORT_UPGRADES)}"
            elif role == "JUNGLE":
                jungle_choice = random.choice(list(JUNGLE_ITEMS.items()))
                starter = f"{jungle_choice[0]} → {jungle_choice[1]}"
            else:
                starter = random.choice(STARTER_ITEMS)

            # Select the first skill to max
            first_skill = random.choice(["Q", "W", "E"])

            # Build the embed
            embed = discord.Embed(title=f"🎲 Ultimate Bravery for {user.display_name}", color=discord.Color.gold())
            embed.add_field(name="Role & Champion", value=f"{role or '-'} → **{champion}**", inline=False)
            embed.add_field(name="Summoner Spells & First Max", value=f"{spell1} + {spell2} → First Max: {first_skill}", inline=False)
            embed.add_field(name="Runes", value=f"**{primary_path['name']}**: {primary_keystone['name']}, {', '.join(r['name'] for r in primary_runes)}\n**{secondary_path['name']}**: {', '.join(r['name'] for r in secondary_runes)}", inline=False)
            embed.add_field(name="Starter & Items", value=f"Starter: {starter}\n" + "\n".join(f"- {item}" for item in build_items), inline=False)

            log.info(f"Generated build for {user.display_name}: Champion - {champion}, Role - {role}")
            return embed, champion, role
        except Exception as e:
            # Log and handle unexpected errors
            log.error(f"Error generating build for {user.display_name}: {e}")
            return None, None, None

class JoinView(discord.ui.View):
    # View for the Ultimate Bravery lobby where players can join or generate builds
    def __init__(self, cog, host_id, mode):
        super().__init__(timeout=None)
        self.cog = cog  # Reference to the parent cog
        self.host_id = host_id  # ID of the host who started the event
        self.mode = mode  # Game mode (e.g., Summoner's Rift or ARAM)
        self.players = []  # List of players who joined the lobby

    @discord.ui.button(label="Join", style=discord.ButtonStyle.green)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Handles a player joining the lobby
        if interaction.user.id not in [u.id for u in self.players]:
            # Add the player to the list if they haven't joined yet
            self.players.append(interaction.user)
            await interaction.response.edit_message(
                content=f"Ultimate Bravery started! Participants: {', '.join([u.display_name for u in self.players])}",
                view=self
            )
            log.info(f"{interaction.user.display_name} joined the Ultimate Bravery lobby.")
        else:
            # Notify the player if they have already joined
            await interaction.response.send_message("You have already joined!", ephemeral=True)

    @discord.ui.button(label="Generate Builds", style=discord.ButtonStyle.blurple)
    async def generate(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Handles generating builds for all players in the lobby
        if interaction.user.id != self.host_id:
            # Only the host can generate builds
            await interaction.response.send_message("Only the host can generate builds!", ephemeral=True)
            return

        if not self.players:
            # Ensure there are players in the lobby
            await interaction.response.send_message("No players in the lobby!", ephemeral=True)
            return

        try:
            taken_champs = []  # List of champions already assigned
            taken_roles = []  # List of roles already assigned (for Summoner's Rift)
            for player in self.players:
                # Generate a build for each player
                embed, champ, role = await self.cog.generate_build(player, self.mode, taken_champs, taken_roles)
                await interaction.channel.send(
                    content=player.mention,
                    embed=embed,
                    view=RerollView(self.cog, player, self.mode, taken_champs.copy(), taken_roles.copy())
                )
                log.info(f"Generated build for {player.display_name}: Champion - {champ}, Role - {role}")

            # Disable all buttons in the lobby after builds are generated
            for child in self.children:
                child.disabled = True

            await interaction.message.edit(content="❗ **Lobby closed. Builds have been generated.**", view=self)
        except Exception as e:
            # Log and handle unexpected errors
            log.error(f"Error generating builds: {e}")
            await interaction.response.send_message("An error occurred while generating builds. Please try again later.", ephemeral=True)

class RerollView(discord.ui.View):
    # View for allowing players to reroll their builds
    def __init__(self, cog, player, mode, taken_champs, taken_roles):
        super().__init__(timeout=900)  # Timeout after 15 minutes
        self.cog = cog  # Reference to the parent cog
        self.player = player  # The player who owns this view
        self.mode = mode  # Game mode (e.g., Summoner's Rift or ARAM)
        self.taken_champs = taken_champs  # List of champions already assigned
        self.taken_roles = taken_roles  # List of roles already assigned

    @discord.ui.button(label="Reroll my Build", style=discord.ButtonStyle.red)
    async def reroll(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Handles rerolling the player's build
        if interaction.user != self.player:
            # Ensure only the player can reroll their own build
            await interaction.response.send_message("You can only reroll your own build!", ephemeral=True)
            return

        try:
            # Generate a new build for the player
            embed, champ, role = await self.cog.generate_build(self.player, self.mode, self.taken_champs, self.taken_roles)
            await interaction.response.edit_message(embed=embed)
            log.info(f"{self.player.display_name} rerolled their build: Champion - {champ}, Role - {role}")
        except Exception as e:
            # Log and handle unexpected errors
            log.error(f"Error rerolling build for {self.player.display_name}: {e}")
            await interaction.response.send_message("An error occurred while rerolling your build. Please try again later.", ephemeral=True)

async def setup(bot):
    # Setup function to add the Ultimate Bravery cog to the bot
    try:
        await bot.add_cog(UltimateBravery(bot))
        log.info("Ultimate Bravery cog successfully added to the bot.")
    except Exception as e:
        # Log and handle unexpected errors during setup
        log.error(f"Error setting up Ultimate Bravery cog: {e}")