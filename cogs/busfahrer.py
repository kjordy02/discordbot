import discord
from discord.ext import commands
from discord import app_commands
import random
import json
import os
from logger import get_logger
from config import SAVE_FOLDER
from datetime import datetime

log = get_logger(__name__)

class Busfahrer(commands.GroupCog, name="busfahrer"):
    def __init__(self, bot):
        self.bot = bot
        self.sessions = {}

    @commands.Cog.listener()
    async def on_ready(self):
        log.info("Busfahrer Modul geladen")


    class GameSession:
        def __init__(self, host):
            self.host = host
            self.players = []
            self.started = False
            self.deck = []
            self.round = 1
            self.current_player_index = 0
            self.cards = {}  # user_id -> list of drawn cards
            self.points = {}
            self.results = {}
            self.game_message = None
            self.awaiting_continue = False

    def generate_deck(self):
        suits = ["❤️", "♠️", "♦️", "♣️"]
        values = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
        deck = [f"{v}{s}" for v in values for s in suits]
        random.shuffle(deck)
        return deck

    def card_value(self, card):
        value = ''.join(filter(str.isdigit, card)) or card[0]
        order = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
        return order.index(value)

    def card_color(self, card):
        return "rot" if "❤️" in card or "♦️" in card else "schwarz"

    def card_suit(self, card):
        if "❤️" in card: return "Herz"
        if "♦️" in card: return "Karo"
        if "♠️" in card: return "Pik"
        if "♣️" in card: return "Kreuz"

    @app_commands.command(name="v2", description="Starte Busfahrer 2.0")
    async def start_busfahrer(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        if guild_id in self.sessions:
            await interaction.response.send_message("Es läuft bereits eine Runde!", ephemeral=True)
            return

        session = self.GameSession(interaction.user)
        self.sessions[guild_id] = session
        view = LobbyView(self, guild_id)

        embed = discord.Embed(title="Busfahrer Lobby", description="Spieler:\n*(niemand)*", color=discord.Color.orange())
        await interaction.response.send_message(embed=embed, view=view)
        session.game_message = await interaction.original_response()
    
    @app_commands.command(name="rangliste", description="Zeige die Busfahrer Gesamtrangliste")
    async def rangliste(self, interaction: discord.Interaction):
        rankings = Rankings(self.bot, interaction.guild.id)
        ranking_text = rankings.get_ranking(daily=False)
        await interaction.response.send_message(f"**Busfahrer Gesamtrangliste:**\n\n{ranking_text}")

    @app_commands.command(name="tagesrangliste", description="Zeige die Busfahrer Tagesrangliste")
    async def tagesrangliste(self, interaction: discord.Interaction):
        rankings = Rankings(self.bot, interaction.guild.id)
        ranking_text = rankings.get_ranking(daily=True)
        await interaction.response.send_message(f"**Busfahrer Tagesrangliste:**\n\n{ranking_text}")


    async def update_lobby(self, guild_id):
        session = self.sessions[guild_id]
        player_list = "\n".join([p.display_name for p in session.players]) or "*niemand*"

        embed = discord.Embed(title="Busfahrer Lobby", description=f"Spieler:\n{player_list}", color=discord.Color.orange())
        await session.game_message.edit(embed=embed, view=LobbyView(self, guild_id))

    async def start_game(self, guild_id, channel):
        session = self.sessions[guild_id]
        session.started = True
        session.deck = self.generate_deck()

        for player in session.players:
            session.cards[player.id] = []
            session.points[player.id] = 0
            session.results[player.id] = ""

        await self.next_turn(guild_id, channel)

    async def next_turn(self, guild_id, channel):
        session = self.sessions[guild_id]

        if session.current_player_index >= len(session.players):
            session.round += 1
            session.current_player_index = 0

        if session.round > 4:
            await self.finish_game(channel, session)
            return

        session.awaiting_continue = False
        player = session.players[session.current_player_index]
        session.results[player.id] = ""
        embed = self.build_embed(session, player)
        view = GameView(self, guild_id, player, session.round, awaiting_answer=True, channel=channel)

        if session.game_message is None:
            session.game_message = await channel.send(embed=embed, view=view)
        else:
            await session.game_message.edit(embed=embed, view=view)

    def build_embed(self, session, player):
        embed = discord.Embed(
            title="🚌 Busfahrer 2.0",
            description=f"Aktueller Spieler: 🚌 **{player.display_name}**",
            color=discord.Color.gold()
        )

        cards = session.cards.setdefault(player.id, [])
        card_text = " ".join(cards) if cards else "*Keine*"
        embed.add_field(name="Gezogene Karten", value=card_text, inline=False)

        points_text = "\n".join([
            f"**🚌 {p.display_name}: {session.points[p.id]} Punkte**" if p == player else f"{p.display_name}: {session.points[p.id]} Punkte"
            for p in session.players
        ])
        embed.add_field(name="Punkte", value=points_text, inline=False)

        result = session.results.get(player.id, "")
        embed.add_field(name="Ergebnis", value=result or "Noch keine Antwort.", inline=False)

        embed.set_footer(text=f"Runde {session.round}/4")
        return embed

    async def resolve_turn(self, guild_id, player, guess, interaction):
        session = self.sessions[guild_id]
        cards = session.cards.setdefault(player.id, [])

        next_card = session.deck.pop()
        cards.append(next_card)

        result = False
        penalty = 0
        points = 0
        drink_text = ""

        if session.round == 1:
            result = guess == self.card_color(next_card)
            penalty = 1
            points = 10 if result else 0
        elif session.round == 2:
            if len(cards) < 2:
                return await interaction.response.send_message("Keine Vergleichskarte!", ephemeral=True)
            prev = self.card_value(cards[-2])
            cur = self.card_value(next_card)
            penalty = 2
            if guess == "gleich":
                result = prev == cur
                points = 20 if result else -10
            elif guess == "höher":
                result = cur > prev
                points = 10 if result else 0
            else:
                result = cur < prev
                points = 10 if result else 0
        elif session.round == 3:
            vals = [self.card_value(c) for c in cards[:-1]]
            min_val, max_val = min(vals), max(vals)
            cur = self.card_value(next_card)
            penalty = 3
            if cur in vals:
        # Gleich hat Vorrang!
                result = guess == "gleich"
                points = 20 if result else 0
            else:
                if guess == "außerhalb":
                    result = cur < min_val or cur > max_val
                    points = 10 if result else 0
                elif guess == "innerhalb":
                    result = min_val < cur < max_val  # Kein Gleich möglich!
                    points = 10 if result else 0
        elif session.round == 4:
            result = guess == self.card_suit(next_card)
            penalty = 4
            points = 30 if result else 0

        session.points[player.id] += points

        if result:
            drink_text = f"✅ Richtig! {'Verteile' if points > 0 else 'Keine Aktion.'} {penalty * 2 if (('gleich' in guess) or (session.round == 4)) else penalty} Schlücke."
        else:
            drink_text = f"❌ Falsch! Trink {penalty * (2 if guess == 'gleich' else 1)} Schlücke."

        session.results[player.id] = drink_text
        session.awaiting_continue = True

        embed = self.build_embed(session, player)
        view = GameView(self, guild_id, player, session.round, awaiting_answer=False, channel=interaction.channel)

        await interaction.response.edit_message(embed=embed, view=view)

    async def finish_game(self, channel, session):
        losers = sorted(session.points.items(), key=lambda x: x[1])
        lowest = losers[0][1]
        candidates = [uid for uid, points in losers if points == lowest]
        busfahrer = random.choice(candidates)

        busfahrer_user = discord.utils.get(channel.guild.members, id=busfahrer)

        embed = discord.Embed(
            title="🚍 Busfahrer gewählt!",
            description=f"**{busfahrer_user.display_name} ist der Busfahrer und muss fahren!**\n\nDrücke unten, um die Fahrt zu starten.",
            color=discord.Color.red()
        )

        view = BusfahrerStartView(self, channel, busfahrer_user)

        await session.game_message.edit(embed=embed, view=view)

### Views and Buttons

class BusfahrerStartView(discord.ui.View):
    def __init__(self, cog, channel, player):
        super().__init__(timeout=None)
        self.cog = cog
        self.channel = channel
        self.player = player

    @discord.ui.button(label="Fahrt antreten 🚍", style=discord.ButtonStyle.green)
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.player:
            await interaction.response.send_message("Nur der Busfahrer kann starten!", ephemeral=True)
            return

        await interaction.response.defer()

        # BusfahrerEndgame starten!
        endgame = BusfahrerEndgame(self.cog, self.channel, self.player, interaction.message)
        await endgame.start()

class LobbyView(discord.ui.View):
    def __init__(self, cog, guild_id):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id

    @discord.ui.button(label="Join", style=discord.ButtonStyle.green)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = self.cog.sessions[self.guild_id]
        if interaction.user not in session.players:
            session.players.append(interaction.user)
        await self.cog.update_lobby(self.guild_id)
        await interaction.response.defer()

    @discord.ui.button(label="Leave", style=discord.ButtonStyle.red)
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = self.cog.sessions[self.guild_id]
        if interaction.user in session.players:
            session.players.remove(interaction.user)
        await self.cog.update_lobby(self.guild_id)
        await interaction.response.defer()

    @discord.ui.button(label="Start", style=discord.ButtonStyle.blurple)
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = self.cog.sessions[self.guild_id]
        if interaction.user != session.host:
            await interaction.response.send_message("Nur der Host kann starten.", ephemeral=True)
            return

        if len(session.players) < 2:
            await interaction.response.send_message("Mindestens 2 Spieler nötig.", ephemeral=True)
            return

        await self.cog.start_game(self.guild_id, interaction.channel)

class GameView(discord.ui.View):
    def __init__(self, cog, guild_id, player, round_num, awaiting_answer, channel):
        timeout = 5 if not awaiting_answer else None
        super().__init__(timeout=timeout)
        self.cog = cog
        self.guild_id = guild_id
        self.player = player
        self.round = round_num
        self.awaiting_answer = awaiting_answer
        self.next_button = None
        self.channel = channel

        if awaiting_answer:
            options = []
            if round_num == 1:
                options = [("rot", "🔴", None), ("schwarz", "⚫", None)]
            elif round_num == 2:
                options = [("höher", "🔼", None), ("gleich", "🟰", None), ("tiefer", "🔽", None)]
            elif round_num == 3:
                options = [("außerhalb", None, "Außerhalb"), ("gleich", "🟰", None), ("innerhalb", None, "Innerhalb")]
            elif round_num == 4:
                options = [("Herz", "❤️", None), ("Karo", "♦️", None), ("Pik", "♠️", None), ("Kreuz", "♣️", None)]

            for value, emoji, text in options:
                self.add_item(GameButton(value, emoji, text, self))
        else:
            next_button = NextButton(self)
            self.next_button = next_button
            self.add_item(next_button)
        
    async def on_timeout(self):
        # Wird automatisch nach timeout ausgeführt
        if self.next_button:
            await self.next_button.auto_continue()

class GameButton(discord.ui.Button):
    def __init__(self, label, emoji, text_label, view):
        super().__init__(label=text_label if text_label else (emoji if emoji else label.capitalize()), style=discord.ButtonStyle.primary)
        self.value = label
        self.view_ref = view

    async def callback(self, interaction: discord.Interaction):
        if interaction.user != self.view_ref.player:
            await interaction.response.send_message("Nicht dein Zug!", ephemeral=True)
            return
        await self.view_ref.cog.resolve_turn(self.view_ref.guild_id, self.view_ref.player, self.value, interaction)

class NextButton(discord.ui.Button):
    def __init__(self, view):
        super().__init__(label="Weiter ➡️", style=discord.ButtonStyle.success)
        self.view_ref = view

    async def callback(self, interaction: discord.Interaction):
        if interaction.user != self.view_ref.player:
            await interaction.response.send_message("Nur der aktuelle Spieler kann weiterklicken.", ephemeral=True)
            return
        await interaction.response.defer()

        self.view_ref.stop()  # WICHTIG → damit der Timer nicht mehr feuert
        
        await self.continue_game(interaction.channel)

    async def auto_continue(self):
        # Auto Continue wird von on_timeout aufgerufen
        await self.continue_game(self.view_ref.channel)

    async def continue_game(self, channel):
        session = self.view_ref.cog.sessions[self.view_ref.guild_id]
        session.current_player_index += 1
        await self.view_ref.cog.next_turn(self.view_ref.guild_id, channel)

### ENDGAME
class BusfahrerEndgame:
    def __init__(self, cog, channel, player, message):
        self.cog = cog
        self.channel = channel
        self.player = player
        self.message = message

        self.current_step = 0
        self.tries = 1
        self.sips = 0

        self.max_steps = 5
        self.top_cards = self.generate_top_cards()
        self.bottom_card = None
        self.file_path = "./save_data/busfahrer_scores.json"
        self.drawn_cards = []
        self.highest_step = 0  # höchste geschaffte Ebene
        self.status_message = ""

    def generate_top_cards(self):
        deck = self.cog.generate_deck()
        return [deck.pop() for _ in range(self.max_steps)]

    def draw_bottom_card(self):
        deck = self.cog.generate_deck()
        return deck.pop()

    async def start(self):
        await self.send_embed()

    async def send_embed(self):
        embed = discord.Embed(
            title="🚍 Busfahrerfahrt",
            description=f"**Busfahrer:** {self.player.display_name}",
            color=discord.Color.red()
        )

        # Kartenanzeige
        card_display = ""
        for i, card in enumerate(self.top_cards):
            if i < self.highest_step+1:
                card_display += f"{card} "
            else:
                card_display += "❓ "
        embed.add_field(name="Karten", value=card_display, inline=False)

        # Gezogene Karten HIER hinzufügen:
        drawn_card_display = " ".join(self.drawn_cards) if self.drawn_cards else "Keine"
        embed.add_field(name="Gezogene Karten", value=drawn_card_display, inline=False)

        if self.status_message:
            embed.add_field(name="Ergebnis", value=self.status_message, inline=False)

        embed.add_field(name="Versuche", value=str(self.tries), inline=True)
        embed.add_field(name="Schlücke getrunken", value=str(self.sips), inline=True)
        embed.add_field(name="Stufe", value=str(self.current_step + 1), inline=True)

        if self.current_step >= self.max_steps:
            embed.description += "\n\n🎉 **Du hast es geschafft!**"

            # SCORE SPEICHERN
            rankings = Rankings(self.cog.bot, self.channel.guild.id)
            rankings.add_result(self.player.id, tries=self.tries, sips=self.sips)

            view = None
            del self.cog.sessions[self.channel.guild.id]
            
        else:
            if self.status_message:
                view = BusfahrerRetryView(self)  # NEU → zeigt Retry Button
            elif self.current_step >= self.max_steps:
                view = None  # Spiel vorbei → kein Button mehr
            else:
                view = BusfahrerGameView(self)  # Raten geht weiter

        await self.message.edit(embed=embed, view=view)

    async def handle_guess(self, interaction, guess):
        if interaction.user != self.player:
            await interaction.response.send_message("Nur der Busfahrer kann spielen!", ephemeral=True)
            return

        if self.current_step >= self.max_steps:
            return

        current_card = self.top_cards[self.current_step]
        self.bottom_card = self.draw_bottom_card()

        prev_value = self.cog.card_value(current_card)
        new_value = self.cog.card_value(self.bottom_card)

        correct = False
        penalty = self.current_step + 1

        if guess == "gleich":
            correct = prev_value == new_value
        elif guess == "höher":
            correct = new_value > prev_value
        elif guess == "tiefer":
            correct = new_value < prev_value

        self.drawn_cards.append(self.bottom_card)

        if correct:
            self.current_step += 1

            if self.current_step > self.highest_step:
                self.highest_step = self.current_step

            if self.current_step >= self.max_steps:
                await self.send_embed()
                return
        else:
            self.status_message = f"❌ Falsch geraten! {penalty} Schlücke trinken."
            self.sips += penalty

            self.current_step = 0
            self.tries += 1

            await self.send_embed() 
            return

        await self.send_embed()

    async def save_score(self):
        data = []
        if os.path.exists(self.file_path):
            with open(self.file_path, "r") as f:
                data = json.load(f)

        found = False
        for entry in data:
            if entry["id"] == self.player.id:
                entry["trys"] = min(entry["trys"], self.tries)
                entry["sips"] = min(entry["sips"], self.sips)
                found = True
                break

        if not found:
            data.append({
                "id": self.player.id,
                "trys": self.tries,
                "sips": self.sips
            })

        with open(self.file_path, "w") as f:
            json.dump(data, f, indent=4)

# Views und Buttons:

class BusfahrerRetryView(discord.ui.View):
    def __init__(self, game):
        super().__init__(timeout=None)
        self.game = game

    @discord.ui.button(label="🔄️ Erneut versuchen", style=discord.ButtonStyle.green)
    async def retry(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.game.player:
            await interaction.response.send_message("Nur der Busfahrer kann weitermachen.", ephemeral=True)
            return

        await interaction.response.defer()

        # Reset → Status + Karten
        self.game.status_message = ""
        self.game.current_step = 0
        self.game.drawn_cards = []

        await self.game.send_embed()


class BusfahrerGameView(discord.ui.View):
    def __init__(self, game):
        super().__init__(timeout=None)
        self.game = game

    @discord.ui.button(emoji="🔼", style=discord.ButtonStyle.primary)
    async def higher(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.game.handle_guess(interaction, "höher")

    @discord.ui.button(emoji="🟰", style=discord.ButtonStyle.primary)
    async def equal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.game.handle_guess(interaction, "gleich")

    @discord.ui.button(emoji="🔽", style=discord.ButtonStyle.primary)
    async def lower(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.game.handle_guess(interaction, "tiefer")


### RANKINGS
class Rankings:
    def __init__(self, bot, guild_id):
        self.bot = bot
        os.makedirs(SAVE_FOLDER, exist_ok=True)

        self.total_file = os.path.join(SAVE_FOLDER, f"{guild_id}_busfahrer_scores.json")
        self.daily_file = os.path.join(SAVE_FOLDER, f"{guild_id}_busfahrer_daily.json")

    def _load(self, filename):
        if not os.path.exists(filename):
            return {}
        with open(filename, "r") as f:
            return json.load(f)

    def _save(self, filename, data):
        with open(filename, "w") as f:
            json.dump(data, f)

    def _reset_daily_if_needed(self):
        now = datetime.now()
        if now.hour >= 12:
            if not os.path.exists(self.daily_file):
                return
            mtime = datetime.fromtimestamp(os.path.getmtime(self.daily_file))
            if mtime.date() != now.date():
                self._save(self.daily_file, {})  # Reset

    def add_result(self, user_id, tries, sips):
        user_id = str(user_id)

        self._reset_daily_if_needed()

        # Gesamt
        total = self._load(self.total_file)
        if user_id not in total:
            total[user_id] = {"tries": 0, "sips": 0}
        total[user_id]["tries"] += tries
        total[user_id]["sips"] += sips
        self._save(self.total_file, total)

        # Tagesliste
        daily = self._load(self.daily_file)
        if user_id not in daily:
            daily[user_id] = {"tries": 0, "sips": 0}
        daily[user_id]["tries"] += tries
        daily[user_id]["sips"] += sips
        self._save(self.daily_file, daily)

    def get_ranking(self, daily=False, limit=10):
        filename = self.daily_file if daily else self.total_file
        data = self._load(filename)

        sorted_data = sorted(data.items(), key=lambda x: (-x[1]["sips"], x[1]["tries"]))

        result = []
        for i, (user_id, stats) in enumerate(sorted_data[:limit], 1):
            user = self.bot.get_user(int(user_id))
            name = user.display_name if user else f"User {user_id}"
            result.append(f"{i}. {name} - {stats['sips']} Schlücke, {stats['tries']} Versuche")
        return "\n".join(result) if result else "Noch keine Einträge."

async def setup(bot):
    await bot.add_cog(Busfahrer(bot))