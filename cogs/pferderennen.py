import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import random
from logger import get_logger
from config import SAVE_FOLDER

log = get_logger(__name__)

class HorseRace(commands.GroupCog, name="horserace"):

    def __init__(self, bot):
        self.bot = bot
        self.sessions = {}
        self.pending_joins = {}

    @commands.Cog.listener()
    async def on_ready(self):
        log.info("HorseRace module loaded")

    class RaceSession:
        def __init__(self, host):
            self.host = host
            self.players = {}  # user_id -> {"member": member, "bet": 0, "horse": None}
            self.started = False
            self.deck = []
            self.progress = {"H": 0, "D": 0, "S": 0, "C": 0}
            self.blockades = []
            self.finished = False
            self.winner = None
            self.reached_levels = {"H": set(), "D": set(), "S": set(), "C": set()}
            self.lobby_view = None

        def generate_deck(self):
            suits = ["H", "D", "S", "C"]
            values = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
            full_deck = [f"{v}{s}" for s in suits for v in values]

            # Asse entfernen (Startpferde)
            for suit in suits:
                full_deck.remove(f"A{suit}")

            # Blockadekarten zufällig ziehen aus den verbliebenen Karten
            blockade_cards = random.sample(full_deck, 4)

            # Diese Karten entfernen
            for card in blockade_cards:
                full_deck.remove(card)

            # Restliches Deck mischen
            random.shuffle(full_deck)

            return full_deck, blockade_cards

    @app_commands.command(name="start", description="Start a horse race drinking game")
    async def start_race(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        if guild_id in self.sessions:
            await interaction.response.send_message("A race is already running!", ephemeral=True)
            return

        session = self.RaceSession(interaction.user)
        self.sessions[guild_id] = session

        view = PregameView(self, guild_id)
        session.lobby_view = view
        embed = discord.Embed(title="🐎 Horse Race Lobby", description="Players can join!", color=discord.Color.green())
        await interaction.response.send_message(embed=embed, view=view)
        session.message = await interaction.original_response()

    async def update_lobby(self, guild_id):
        session = self.sessions[guild_id]

        desc = ""
        for p in session.players.values():
            suit = p["horse"]
            emoji = self.bot.card_emojis[f"A{suit}"]
            desc += f"{p['member'].mention} {emoji} {p['bet']} sips\n"

        if not desc:
            desc = "*No one yet*"

        embed = discord.Embed(title="🐎 Horse Race Lobby", description=desc, color=discord.Color.green())
        await session.message.edit(embed=embed, view=PregameView(self, guild_id))

    async def start_race_game(self, guild_id, channel):
        session = self.sessions[guild_id]

        await session.message.edit(view=None)

        session.started = True
        session.deck, blockade_cards = session.generate_deck()
        session.blockade_targets = [card[-1] for card in blockade_cards]
        session.blockades = ["HIDDEN"] * 4
        session.blockade_revealed = [False] * 4

        await session.message.edit(embed=self.build_race_embed(session), view=None)

        while not session.finished:
            await asyncio.sleep(2)

            if len(session.deck) == 0:
                break

            card = session.deck.pop()
            suit = card[-1]
            value = card[:-1]

            session.progress[suit] += 1
            session.reached_levels[suit].add(session.progress[suit])

            if session.progress[suit] >= 5:
                session.finished = True
                session.winner = suit
                break

            for blockade_index in range(4):
                if not session.blockade_revealed[blockade_index]:
                    blockade_level = blockade_index + 1

                    if all(blockade_level in levels for levels in session.reached_levels.values()):
                        target = session.blockade_targets[blockade_index]
                        session.blockades[blockade_index] = self.bot.card_emojis[f"{target}"]
                        session.blockade_revealed[blockade_index] = True

                        await session.message.edit(embed=self.build_race_embed(session, reset=target, last_card=card), view=None)
                        await asyncio.sleep(2)

                        session.progress[target] = 0
                        await session.message.edit(embed=self.build_race_embed(session, reset=target, last_card=card), view=None)

                        break

            await session.message.edit(embed=self.build_race_embed(session, last_card=card), view=None)

        await self.finish_race(guild_id, channel)

    def build_race_embed(self, session, reset=None, last_card=None):
        embed = discord.Embed(title="🐎 Horse Race in Progress...", color=discord.Color.blue())

        bets = []
        for p in session.players.values():
            suit = p["horse"]
            emoji = self.bot.card_emojis[f"A{suit}"]
            bets.append(f"{p['member'].mention} ({emoji} - {p['bet']} sips)")
        embed.add_field(name="💰 Bets", value="\n".join(bets), inline=False)

        if last_card:
            emoji = self.bot.card_emojis[last_card]
            embed.add_field(name="🃏 Last Card", value=emoji, inline=False)

        blockade_line = "⬛"
        for blockade_card in session.blockades:
            blockade_line += blockade_card if blockade_card != "HIDDEN" else self.bot.card_emojis["back"]
        blockade_line += "👑"
        embed.add_field(name="⠀", value=blockade_line, inline=False)

        suit_names = {"H": "Hearts", "D": "Diamonds", "S": "Spades", "C": "Clubs"}
        for suit in ["H", "D", "S", "C"]:
            if session.progress[suit] == 0:
                line = self.bot.card_emojis[f"A{suit}"]
            else:
                line = "⬜"

            for i in range(1, 6):
                if session.progress[suit] == i:
                    line += self.bot.card_emojis[f"A{suit}"]
                elif i == 5:
                    line += "👑" if session.finished and suit == session.winner else "🟩"
                else:
                    line += "⬜"

            embed.add_field(name="⠀", value=line, inline=False)

        return embed

    async def finish_race(self, guild_id, channel):
        session = self.sessions[guild_id]
        embed = self.build_race_embed(session)

        result_text = f"🎉 **{self.bot.card_emojis[f'A{session.winner}']} {session.winner} has won!**\n\n"
        winners = []

        for p in session.players.values():
            if p["horse"] == session.winner:
                winners.append((p["member"], p["bet"] * 2))

        if winners:
            result_text += "\n".join([f"{m.mention} can give out **{sips} sips**!" for m, sips in winners])
        else:
            result_text += "Unfortunately, no one bet on the winning horse."

        embed.add_field(name="🏆 Result", value=result_text, inline=False)
        await session.message.edit(embed=embed, view=None)
        del self.sessions[guild_id]

# --------------------- VIEWS ----------------------------

class PregameView(discord.ui.View):
    def __init__(self, cog, guild_id):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id

    @discord.ui.button(label="Join", style=discord.ButtonStyle.green)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = self.cog.sessions[self.guild_id]

        if interaction.user.id in session.players:
            await interaction.response.send_message("You are already in the lobby!", ephemeral=True)
            return

        if self.guild_id not in self.cog.pending_joins:
            self.cog.pending_joins[self.guild_id] = {}

        self.cog.pending_joins[self.guild_id][interaction.user.id] = {"horse": None, "bet": None}

        await interaction.response.send_message(
            "Please choose your horse and bet to join the lobby:",
            view=PlayerJoinSelectionView(self.cog, self.guild_id, interaction.user.id),
            ephemeral=True
        )

    @discord.ui.button(label="Leave", style=discord.ButtonStyle.red)
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = self.cog.sessions[self.guild_id]
        if interaction.user.id in session.players:
            del session.players[interaction.user.id]
        await self.cog.update_lobby(self.guild_id)
        await interaction.response.defer()

    @discord.ui.button(label="Start", style=discord.ButtonStyle.blurple)
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = self.cog.sessions[self.guild_id]

        if interaction.user != session.host:
            await interaction.response.send_message("Only the host can start!", ephemeral=True)
            return

        if not session.players:
            await interaction.response.send_message("There are no players in the lobby!", ephemeral=True)
            return

        session.lobby_view.stop()
        await session.message.edit(view=None)
        await self.cog.start_race_game(self.guild_id, interaction.channel)

class PlayerJoinSelectionView(discord.ui.View):
    def __init__(self, cog, guild_id, player_id):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id
        self.player_id = player_id

        self.add_item(PlayerHorseDropdown(cog, guild_id, player_id, locked=False))
        self.add_item(PlayerBetDropdown(cog, guild_id, player_id, locked=False))
        self.add_item(PlayerJoinConfirmButton(cog, guild_id, player_id))

class PlayerJoinConfirmButton(discord.ui.Button):
    def __init__(self, cog, guild_id, player_id):
        super().__init__(label="Join", style=discord.ButtonStyle.success)
        self.cog = cog
        self.guild_id = guild_id
        self.player_id = player_id

    async def callback(self, interaction: discord.Interaction):
        session = self.cog.sessions[self.guild_id]

        guild_pending = self.cog.pending_joins.get(self.guild_id, {})
        pending = guild_pending.get(self.player_id)

        if not pending:
            await interaction.response.send_message("Your join session has expired. Please try again.", ephemeral=True)
            return

        if not pending["horse"] or not pending["bet"]:
            await interaction.response.send_message("Please choose your horse and bet first!", ephemeral=True)
            return

        session.players[self.player_id] = {
            "member": interaction.user,
            "bet": pending["bet"],
            "horse": pending["horse"],
            "locked": True
        }

        del self.cog.pending_joins[self.guild_id][self.player_id]
        await self.cog.update_lobby(self.guild_id)

        self.view.stop()
        await interaction.response.defer(ephemeral=True)

class PlayerHorseDropdown(discord.ui.Select):
    def __init__(self, cog, guild_id, player_id, locked):
        session = cog.sessions[guild_id]
        player_data = session.players.get(player_id, {})
        current = player_data.get("horse", None)

        options = [
            discord.SelectOption(label="Hearts", value="H", emoji="❤️", default=(current == "H")),
            discord.SelectOption(label="Diamonds", value="D", emoji="♦️", default=(current == "D")),
            discord.SelectOption(label="Spades", value="S", emoji="♠️", default=(current == "S")),
            discord.SelectOption(label="Clubs", value="C", emoji="♣️", default=(current == "C")),
        ]

        super().__init__(placeholder="Choose your horse", min_values=1, max_values=1, options=options, disabled=locked)
        self.cog = cog
        self.guild_id = guild_id
        self.player_id = player_id

    async def callback(self, interaction: discord.Interaction):
        pending = self.cog.pending_joins[self.guild_id][self.player_id]
        pending["horse"] = self.values[0]
        await interaction.response.defer()

class PlayerBetDropdown(discord.ui.Select):
    def __init__(self, cog, guild_id, player_id, locked):
        session = cog.sessions[guild_id]
        player_data = session.players.get(player_id, {})
        current = player_data.get("bet", None)

        options = [discord.SelectOption(label=f"{i} sips", value=str(i), default=(current == i)) for i in range(1, 11)]
        super().__init__(placeholder="Choose sips", min_values=1, max_values=1, options=options, disabled=locked)

        self.cog = cog
        self.guild_id = guild_id
        self.player_id = player_id

    async def callback(self, interaction: discord.Interaction):
        pending = self.cog.pending_joins[self.guild_id][self.player_id]
        pending["bet"] = int(self.values[0])
        await interaction.response.defer()

# --------------------- SETUP ----------------------------

async def setup(bot):
    await bot.add_cog(HorseRace(bot))