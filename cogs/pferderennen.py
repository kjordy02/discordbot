import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import random
from logger import get_logger
from config import SAVE_FOLDER

log = get_logger(__name__)

class Pferderennen(commands.GroupCog, name="pferderennen"):

    def __init__(self, bot):
        self.bot = bot
        self.sessions = {}
        self.pending_joins = {}

    @commands.Cog.listener()
    async def on_ready(self):
        log.info("Pferderennen Modul geladen")

    class RaceSession:
        def __init__(self, host):
            self.host = host
            self.players = {}  # user_id -> {"member": member, "einsatz": 0, "pferd": None}
            self.started = False
            self.deck = []
            self.progress = {"Herz": 0, "Karo": 0, "Pik": 0, "Kreuz": 0}
            self.blockades = []
            self.finished = False
            self.winner = None
            self.reached_levels = {"Herz": set(), "Karo": set(), "Pik": set(), "Kreuz": set()}
            self.lobby_view = None

        def generate_deck(self):
            suits = ["Herz", "Karo", "Pik", "Kreuz"]
            values = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
            deck = [f"{v} {s}" for s in suits for v in values]
            for suit in suits:
                deck.remove(f"A {suit}")
            random.shuffle(deck)
            return deck

    @app_commands.command(name="start", description="Starte ein Pferderennen Trinkspiel")
    async def start_race(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        if guild_id in self.sessions:
            await interaction.response.send_message("Es läuft bereits ein Rennen!", ephemeral=True)
            return

        session = self.RaceSession(interaction.user)
        self.sessions[guild_id] = session

        view = PregameView(self, guild_id)
        session.lobby_view = view
        embed = discord.Embed(title="🐎 Pferderennen Lobby", description="Spieler können beitreten!", color=discord.Color.green())
        await interaction.response.send_message(embed=embed, view=view)
        session.message = await interaction.original_response()

    async def update_lobby(self, guild_id):
        session = self.sessions[guild_id]
        
        desc = ""
        for p in session.players.values():
            desc += f"{p['member'].mention} {self.get_symbol(p['pferd'])} {p['einsatz']} Schlücke\n"

        if not desc:
            desc = "*Niemand*"

        embed = discord.Embed(title="🐎 Pferderennen Lobby", description=desc, color=discord.Color.green())
        await session.message.edit(embed=embed, view=PregameView(self, guild_id))

    def get_symbol(self, suit):
        return {
            "Herz": "❤️",
            "Karo": "♦️",
            "Pik": "♠️",
            "Kreuz": "♣️"
        }[suit]

    async def start_race_game(self, guild_id, channel):
        session = self.sessions[guild_id]

        # Entferne die Setzen-View
        await session.message.edit(view=None)

        session.started = True
        session.deck = session.generate_deck()
        session.blockades = ["HIDDEN", "HIDDEN", "HIDDEN", "HIDDEN"]
        session.blockade_targets = random.sample(["Herz", "Karo", "Pik", "Kreuz"], 4)
        session.blockade_revealed = [False, False, False, False]

        await session.message.edit(embed=self.build_race_embed(session), view=None)

        while not session.finished:
            await asyncio.sleep(2)

            if len(session.deck) == 0:
                break

            card = session.deck.pop()
            _, suit = card.split()

            session.progress[suit] += 1

            # NEU → Level als erreicht markieren
            session.reached_levels[suit].add(session.progress[suit])

            # Check Ziel
            if session.progress[suit] >= 5:
                session.finished = True
                session.winner = suit
                break

            # Prüfen ob eine Blockade umgedreht werden muss
            for blockade_index in range(4):
                if not session.blockade_revealed[blockade_index]:
                    blockade_ebene = blockade_index + 1

                    if all(blockade_ebene in levels for levels in session.reached_levels.values()):
                        target = session.blockade_targets[blockade_index]
                        session.blockades[blockade_index] = f"{self.get_symbol(target)}"
                        session.blockade_revealed[blockade_index] = True

                        # ANZEIGEN BEVOR reset
                        await session.message.edit(embed=self.build_race_embed(session, reset=target, last_card=card), view=None)
                        await asyncio.sleep(2)

                        # JETZT resetten
                        session.progress[target] = 0  # Reset
                        await session.message.edit(embed=self.build_race_embed(session, reset=target, last_card=card), view=None)

                        blockade_triggered = True
                        break  # Nur eine Blockade pro Runde

                await session.message.edit(embed=self.build_race_embed(session, last_card=card), view=None)

        await self.finish_race(guild_id, channel)

    def build_race_embed(self, session, reset=None, last_card=None):
        embed = discord.Embed(title="🐎 Pferderennen läuft...", color=discord.Color.blue())

        # Einsätze anzeigen
        bets = []
        for p in session.players.values():
            bets.append(f"{p['member'].mention} ({p['pferd']} - {p['einsatz']} Schlücke)")
        embed.add_field(name="💰 Einsätze", value="\n".join(bets), inline=False)

        # Letzte Karte anzeigen
        if last_card:
            embed.add_field(name="🃏 Letzte Karte", value=last_card, inline=False)

        # Blockaden oben anzeigen (schön aligned)
        blockade_line = "⬛"  # <--- Emoji Platzhalter
        for blockade_card in session.blockades:
            blockade_line += blockade_card if blockade_card != "HIDDEN" else "❓"
        blockade_line += "👑"
        embed.add_field(name="⠀", value=blockade_line, inline=False)

        # Rennfeld anzeigen
        for suit in ["Herz", "Karo", "Pik", "Kreuz"]:
            if session.progress[suit] == 0:
                line = f"{self.get_symbol(suit)}"
            else:
                line = "⬜"

            for i in range(1, 6):
                if session.progress[suit] == i:
                    line += self.get_symbol(suit)
                elif i == 5:
                    line += "👑" if session.finished and suit == session.winner else "🟩"
                else:
                    line += "⬜"

            embed.add_field(name="⠀", value=line, inline=False)

        return embed

    async def finish_race(self, guild_id, channel):
        session = self.sessions[guild_id]

        # Embed Grundgerüst
        embed = self.build_race_embed(session)

        # Gewinnertext vorbereiten
        result_text = f"🎉 **{self.get_symbol(session.winner)} {session.winner} hat gewonnen!**\n\n"
        winners = []

        for p in session.players.values():
            if p["pferd"] == session.winner:
                winners.append((p["member"], p["einsatz"] * 2))

        if winners:
            result_text += "\n".join([f"{m.mention} darf **{sips} Schlücke** verteilen!" for m, sips in winners])
        else:
            result_text += "Leider hat niemand auf das Gewinnerpferd gesetzt."

        # Extra Ergebnis Feld anhängen
        embed.add_field(name="🏆 Ergebnis", value=result_text, inline=False)

        # Embed senden + View entfernen
        await session.message.edit(embed=embed, view=None)

        # Sitzung beenden
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

        # Prüfen ob der User schon in der Lobby ist
        if interaction.user.id in session.players:
            await interaction.response.send_message("Du bist bereits in der Lobby!", ephemeral=True)
            return

        if self.guild_id not in self.cog.pending_joins:
            self.cog.pending_joins[self.guild_id] = {}

        self.cog.pending_joins[self.guild_id][interaction.user.id] = {"pferd": None, "einsatz": None}

        # Statt direkt hinzufügen → ephemeral Auswahl anzeigen
        await interaction.response.send_message(
            "Bitte wähle dein Pferd und Einsatz um der Lobby beizutreten:",
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
            await interaction.response.send_message("Nur der Host kann starten!", ephemeral=True)
            return

        if not session.players:
            await interaction.response.send_message("Es sind keine Spieler in der Lobby!", ephemeral=True)
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

        self.add_item(PlayerPferdDropdown(cog, guild_id, player_id, locked=False))
        self.add_item(PlayerSchluckDropdown(cog, guild_id, player_id, locked=False))
        self.add_item(PlayerJoinConfirmButton(cog, guild_id, player_id))

class PlayerJoinConfirmButton(discord.ui.Button):
    def __init__(self, cog, guild_id, player_id):
        super().__init__(label="Beitreten", style=discord.ButtonStyle.success)
        self.cog = cog
        self.guild_id = guild_id
        self.player_id = player_id

    async def callback(self, interaction: discord.Interaction):
        session = self.cog.sessions[self.guild_id]

        pending = self.cog.pending_joins[self.guild_id][self.player_id]

        if not pending["pferd"] or not pending["einsatz"]:
            await interaction.response.send_message("Bitte wähle zuerst Pferd und Einsatz!", ephemeral=True)
            return

        session.players[self.player_id] = {
            "member": interaction.user,
            "einsatz": pending["einsatz"],
            "pferd": pending["pferd"],
            "locked": True
        }

        # Pending löschen
        del self.cog.pending_joins[self.guild_id][self.player_id]
        await self.cog.update_lobby(self.guild_id)

        self.view.stop()

        await interaction.response.defer(ephemeral=True)

class PlayerPferdDropdown(discord.ui.Select):
    def __init__(self, cog, guild_id, player_id, locked):
        session = cog.sessions[guild_id]
        player_data = session.players.get(player_id, {})
        current = player_data.get("pferd", None)

        options = [
            discord.SelectOption(label="Herz", emoji="❤️", default=(current == "Herz")),
            discord.SelectOption(label="Karo", emoji="♦️", default=(current == "Karo")),
            discord.SelectOption(label="Pik", emoji="♠️", default=(current == "Pik")),
            discord.SelectOption(label="Kreuz", emoji="♣️", default=(current == "Kreuz")),
        ]

        super().__init__(placeholder="Pferd wählen", min_values=1, max_values=1, options=options, disabled=locked)
        self.cog = cog
        self.guild_id = guild_id
        self.player_id = player_id

    async def callback(self, interaction: discord.Interaction):
        pending = self.cog.pending_joins[self.guild_id][self.player_id]
        pending["pferd"] = self.values[0]

        await interaction.response.defer()

class PlayerSchluckDropdown(discord.ui.Select):
    def __init__(self, cog, guild_id, player_id, locked):
        session = cog.sessions[guild_id]
        player_data = session.players.get(player_id, {})
        current = player_data.get("einsatz", None)

        options = [discord.SelectOption(label=f"{i} Schlücke", value=str(i), default=(current == i)) for i in range(1, 11)]
        super().__init__(placeholder="Schlücke wählen", min_values=1, max_values=1, options=options, disabled=locked)

        self.cog = cog
        self.guild_id = guild_id
        self.player_id = player_id

    async def callback(self, interaction: discord.Interaction):
        pending = self.cog.pending_joins[self.guild_id][self.player_id]
        pending["einsatz"] = int(self.values[0])

        await interaction.response.defer()

# --------------------- SETUP ----------------------------

async def setup(bot):
    await bot.add_cog(Pferderennen(bot))