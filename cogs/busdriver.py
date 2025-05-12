import discord
from discord.ext import commands
from discord import app_commands
import random
import json
import os
from logger import get_logger
from config import SAVE_FOLDER
from datetime import datetime
from helper.cardgames import generate_standard_deck  # Import the helper function

log = get_logger(__name__)

class Busdriver(commands.GroupCog, name="busdriver"):
    # Main class for the Busdriver game cog
    def __init__(self, bot):
        self.bot = bot
        self.sessions = {}

    @commands.Cog.listener()
    async def on_ready(self):
        # Event listener triggered when the bot is ready
        log.info("Busdriver module successfully loaded and ready.")

    class GameSession:
        def __init__(self, host):
            self.host = host  # The user who started the game
            self.players = []  # List of players in the session
            self.started = False  # Indicates if the game has started
            self.deck = []  # The shuffled deck of cards
            self.round = 1  # Current round of the game
            self.current_player_index = 0  # Index of the current player
            self.cards = {}  # Cards drawn by each player
            self.points = {}  # Points scored by each player
            self.results = {}  # Results of each player's turn
            self.game_message = None  # The game message for interaction
            self.awaiting_continue = False  # Whether the game is waiting for a player to continue

    @app_commands.command(name="v2", description="Start Busdriver 2.0")
    async def start_busdriver(self, interaction: discord.Interaction):
        # Starts a new Busdriver game session
        guild_id = interaction.guild.id
        if guild_id in self.sessions:
            # Prevents starting a new game if one is already running
            await interaction.response.send_message("A game is already running!", ephemeral=True)
            log.warning(f"Attempted to start a new game in guild {interaction.guild.name} while one is already running.")
            return

        try:
            session = self.GameSession(interaction.user)  # Create a new game session
            self.sessions[guild_id] = session
            view = LobbyView(self, guild_id)  # Create a lobby view for players to join

            # Send an embed message to display the lobby
            embed = discord.Embed(title="Busdriver Lobby", description="Players:\n*(no one)*", color=discord.Color.orange())
            await interaction.response.send_message(embed=embed, view=view)
            session.game_message = await interaction.original_response()
            log.info(f"Busdriver game started by {interaction.user.display_name} in guild {interaction.guild.name}.")
        except Exception as e:
            # Log and handle unexpected errors
            log.error(f"Error starting Busdriver game in guild {interaction.guild.name}: {e}")
            await interaction.response.send_message("An error occurred while starting the game. Please try again later.", ephemeral=True)

    @app_commands.command(name="rangliste", description="Show the overall Busdriver ranking")
    async def rangliste(self, interaction: discord.Interaction):
        # Displays the overall ranking for the Busdriver game
        rankings = Rankings(self.bot, interaction.guild.id)
        ranking_text = rankings.get_ranking(daily=False)
        await interaction.response.send_message(f"**Overall Busdriver Ranking:**\n\n{ranking_text}")

    @app_commands.command(name="tagesrangliste", description="Show today's Busdriver ranking")
    async def tagesrangliste(self, interaction: discord.Interaction):
        # Displays today's ranking for the Busdriver game
        rankings = Rankings(self.bot, interaction.guild.id)
        ranking_text = rankings.get_ranking(daily=True)
        await interaction.response.send_message(f"**Today's Busdriver Ranking:**\n\n{ranking_text}")

    async def update_lobby(self, guild_id):
        # Updates the lobby message with the current list of players
        try:
            session = self.sessions[guild_id]
            player_list = "\n".join([p.display_name for p in session.players]) or "*no one*"

            embed = discord.Embed(title="Busdriver Lobby", description=f"Players:\n{player_list}", color=discord.Color.orange())
            await session.game_message.edit(embed=embed, view=LobbyView(self, guild_id))
            log.info(f"Updated lobby for guild {guild_id}.")
        except Exception as e:
            # Log and handle unexpected errors
            log.error(f"Error updating lobby for guild {guild_id}: {e}")

    async def start_game(self, guild_id, channel):
        # Starts the game by initializing the deck and player data
        try:
            session = self.sessions[guild_id]
            session.started = True
            session.deck = generate_standard_deck()  # Generate a shuffled deck

            for player in session.players:
                session.cards[player.id] = []  # Initialize empty card list for each player
                session.points[player.id] = 0  # Initialize points for each player
                session.results[player.id] = ""  # Initialize results for each player

            log.info(f"Game started in guild {guild_id} with {len(session.players)} players.")
            await self.next_turn(guild_id, channel)  # Start the first turn
        except Exception as e:
            # Log and handle unexpected errors
            log.error(f"Error starting game in guild {guild_id}: {e}")
            await channel.send("An error occurred while starting the game. Please try again later.")

    async def next_turn(self, guild_id, channel):
        # Handles the logic for progressing to the next player's turn
        session = self.sessions[guild_id]

        if session.current_player_index >= len(session.players):
            # Move to the next round if all players have taken their turn
            session.round += 1
            session.current_player_index = 0

        if session.round > 4:
            # End the game after 4 rounds
            await self.finish_game(channel, session)
            return

        session.awaiting_continue = False
        player = session.players[session.current_player_index]
        session.results[player.id] = ""  # Reset the result for the current player
        embed = self.build_embed(session, player)  # Build the game UI embed
        view = GameView(self, guild_id, player, session.round, awaiting_answer=True, channel=channel)

        if session.game_message is None:
            # Send the game message if it doesn't exist
            session.game_message = await channel.send(embed=embed, view=view)
        else:
            # Update the existing game message
            await session.game_message.edit(embed=embed, view=view)

    def build_embed(self, session, player):
        # Builds the embed message for the current game state
        embed = discord.Embed(
            title="🚌 Busdriver 2.0",
            description=f"Current player: 🚌 **{player.display_name}**",
            color=discord.Color.gold()
        )

        cards = session.cards.setdefault(player.id, [])
        card_text = " ".join([self.bot.card_emojis.get(card) or f"[{card}]" for card in cards]) if cards else "*None*"
        embed.add_field(name="Drawn cards", value=card_text, inline=False)

        points_text = "\n".join([
            f"**🚌 {p.display_name}: {session.points[p.id]} points**" if p == player else f"{p.display_name}: {session.points[p.id]} points"
            for p in session.players
        ])
        embed.add_field(name="Points", value=points_text, inline=False)

        result = session.results.get(player.id, "")
        embed.add_field(name="Result", value=result or "No answer yet.", inline=False)

        embed.set_footer(text=f"Round {session.round}/4")
        return embed
    
    async def resolve_turn(self, guild_id, player, guess, interaction):
        # Resolves the current player's turn based on their guess
        session = self.sessions[guild_id]
        cards = session.cards.setdefault(player.id, [])

        next_card = session.deck.pop()  # Draw the next card from the deck
        cards.append(next_card)

        result = False
        penalty = 0
        points = 0
        drink_text = ""

        # Extract card value and suit
        value = next_card[:-1]
        suit = next_card[-1]
        color = "red" if suit in ("H", "D") else "black"
        suit_name = {"H": "hearts", "D": "diamonds", "S": "spades", "C": "clubs"}[suit]
        value_order = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]

        # Determine the result based on the current round
        if session.round == 1:
            result = guess == color
            penalty = 1
            points = 10 if result else 0

        elif session.round == 2:
            if len(cards) < 2:
                # Ensure there is a previous card for comparison
                return await interaction.response.send_message("No comparison card available!", ephemeral=True)
            prev = value_order.index(cards[-2][:-1])
            cur = value_order.index(value)
            penalty = 2
            if guess == "equal":
                result = prev == cur
                points = 20 if result else -10
            elif guess == "higher":
                result = cur > prev
                points = 10 if result else 0
            else:
                result = cur < prev
                points = 10 if result else 0

        elif session.round == 3:
            # Handle logic for round 3: inside, outside, or equal
            vals = [value_order.index(c[:-1]) for c in cards[:-1]]
            min_val, max_val = min(vals), max(vals)
            cur = value_order.index(value)
            penalty = 3
            if cur in vals:
                result = guess == "equal"
                points = 20 if result else 0
            else:
                if guess == "outside":
                    result = cur < min_val or cur > max_val
                    points = 10 if result else 0
                elif guess == "inside":
                    result = min_val < cur < max_val
                    points = 10 if result else 0

        elif session.round == 4:
            # Handle logic for round 4: guess the suit
            result = guess == suit_name
            penalty = 4
            points = 30 if result else 0

        session.points[player.id] += points  # Update the player's points

        emoji = self.bot.card_emojis.get(next_card) or f"[{next_card}]"

        # Generate the result text based on whether the guess was correct
        if result:
            drink_text = f"{emoji} ✅ Correct! {'Give' if points > 0 else 'No action.'} {penalty * 2 if (('equal' in guess) or (session.round == 4)) else penalty} sips."
        else:
            drink_text = f"{emoji} ❌ Wrong! Drink {penalty * (2 if guess == 'equal' else 1)} sips."

        session.results[player.id] = drink_text
        session.awaiting_continue = True

        # Update the game embed and view
        embed = self.build_embed(session, player)
        view = GameView(self, guild_id, player, session.round, awaiting_answer=False, channel=interaction.channel)
        await interaction.response.edit_message(embed=embed, view=view)

    async def finish_game(self, channel, session):
        # Ends the game and determines the Busdriver
        try:
            losers = sorted(session.points.items(), key=lambda x: x[1])
            lowest = losers[0][1]
            candidates = [uid for uid, points in losers if points == lowest]
            busdriver = random.choice(candidates)  # Randomly select the Busdriver among the lowest scorers

            busdriver_user = discord.utils.get(channel.guild.members, id=busdriver)

            # Create an embed announcing the Busdriver
            embed = discord.Embed(
                title="🚍 Busdriver chosen!",
                description=f"**{busdriver_user.display_name} is the Busdriver and must drive!**\n\nPress below to start the ride.",
                color=discord.Color.red()
            )

            view = BusdriverStartView(self, channel, busdriver_user)

            # Update the game message with the Busdriver announcement
            await session.game_message.edit(embed=embed, view=view)
            log.info(f"Game finished in guild {channel.guild.name}. Busdriver: {busdriver_user.display_name}.")
        except Exception as e:
            # Log and handle unexpected errors
            log.error(f"Error finishing game in guild {channel.guild.name}: {e}")
            await channel.send("An error occurred while finishing the game. Please try again later.")

### Views and Buttons

class BusdriverStartView(discord.ui.View):
    # View for starting the Busdriver ride
    def __init__(self, cog, channel, player):
        super().__init__(timeout=None)
        self.cog = cog
        self.channel = channel
        self.player = player

    @discord.ui.button(label="Start the ride 🚍", style=discord.ButtonStyle.green)
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Only the Busdriver can start the ride
        if interaction.user != self.player:
            await interaction.response.send_message("Only the Busdriver can start!", ephemeral=True)
            return

        await interaction.response.defer()

        # Start the endgame phase
        endgame = BusdriverEndgame(self.cog, self.channel, self.player, interaction.message)
        await endgame.start()

class LobbyView(discord.ui.View):
    # View for the game lobby where players can join or leave
    def __init__(self, cog, guild_id):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id

    @discord.ui.button(label="Join", style=discord.ButtonStyle.green)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Add the user to the game session
        session = self.cog.sessions[self.guild_id]
        if interaction.user not in session.players:
            session.players.append(interaction.user)
        await self.cog.update_lobby(self.guild_id)
        await interaction.response.defer()

    @discord.ui.button(label="Leave", style=discord.ButtonStyle.red)
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Remove the user from the game session
        session = self.cog.sessions[self.guild_id]
        if interaction.user in session.players:
            session.players.remove(interaction.user)
        await self.cog.update_lobby(self.guild_id)
        await interaction.response.defer()

    @discord.ui.button(label="Start", style=discord.ButtonStyle.blurple)
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Start the game if the user is the host and there are enough players
        session = self.cog.sessions[self.guild_id]
        if interaction.user != session.host:
            await interaction.response.send_message("Only the host can start.", ephemeral=True)
            return

        if len(session.players) < 2:
            await interaction.response.send_message("At least 2 players required.", ephemeral=True)
            return

        await self.cog.start_game(self.guild_id, interaction.channel)

class GameView(discord.ui.View):
    # View for the game interface during a player's turn
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
            # Add buttons for the player's guess based on the current round
            options = []
            if round_num == 1:
                options = [("red", "🔴", None), ("black", "⚫", None)]
            elif round_num == 2:
                options = [("higher", "🔼", None), ("equal", "🟰", None), ("lower", "🔽", None)]
            elif round_num == 3:
                options = [("outside", None, "Outside"), ("equal", "🟰", None), ("inside", None, "Inside")]
            elif round_num == 4:
                options = [("hearts", "❤️", None), ("diamonds", "♦️", None), ("spades", "♠️", None), ("clubs", "♣️", None)]

            for value, emoji, text in options:
                self.add_item(GameButton(value, emoji, text, self))
        else:
            # Add a "Next" button if awaiting the next turn
            next_button = NextButton(self)
            self.next_button = next_button
            self.add_item(next_button)

    async def on_timeout(self):
        # Automatically continue the game if the view times out
        if self.next_button:
            await self.next_button.auto_continue()

class GameButton(discord.ui.Button):
    # Button for making a guess during a player's turn
    def __init__(self, label, emoji, text_label, view):
        super().__init__(label=text_label if text_label else (emoji if emoji else label.capitalize()), style=discord.ButtonStyle.primary)
        self.value = label
        self.view_ref = view

    async def callback(self, interaction: discord.Interaction):
        # Handle the player's guess
        if interaction.user != self.view_ref.player:
            await interaction.response.send_message("Not your turn!", ephemeral=True)
            return
        await self.view_ref.cog.resolve_turn(self.view_ref.guild_id, self.view_ref.player, self.value, interaction)

class NextButton(discord.ui.Button):
    # Button for continuing to the next turn
    def __init__(self, view):
        super().__init__(label="Next ➡️", style=discord.ButtonStyle.success)
        self.view_ref = view

    async def callback(self, interaction: discord.Interaction):
        # Handle the "Next" button click
        if interaction.user != self.view_ref.player:
            await interaction.response.send_message("Only the current player can continue.", ephemeral=True)
            return
        await interaction.response.defer()

        self.view_ref.stop()
        await self.continue_game(interaction.channel)

    async def auto_continue(self):
        # Automatically continue the game
        await self.continue_game(self.view_ref.channel)

    async def continue_game(self, channel):
        # Progress to the next player's turn
        session = self.view_ref.cog.sessions[self.view_ref.guild_id]
        session.current_player_index += 1
        await self.view_ref.cog.next_turn(self.view_ref.guild_id, channel)

class BusdriverEndgame:
    # Handles the endgame phase of the Busdriver game.The Busdriver must complete a series of steps by guessing card values correctly.

    def __init__(self, cog, channel, player, message):
        self.cog = cog  # Reference to the parent cog
        self.channel = channel  # The channel where the game is played
        self.player = player  # The player who is the Busdriver
        self.message = message  # The message object for the game UI

        self.current_step = 0  # The current step the Busdriver is on
        self.tries = 1  # Number of attempts the Busdriver has made
        self.sips = 0  # Total sips the Busdriver has taken

        self.max_steps = 5  # Total number of steps to complete
        self.deck = self.cog.generate_deck()  # Generate a shuffled deck
        self.top_cards = [self.deck.pop() for _ in range(self.max_steps)]  # Cards for the steps
        self.bottom_card = None  # The card drawn for comparison
        self.file_path = "./save_data/busdriver_scores.json"  # Path to save scores
        self.drawn_cards = []  # Cards drawn during the game
        self.highest_step = 0  # The highest step completed
        self.status_message = ""  # Status message for the current step

    def draw_bottom_card(self):
        # Draws the next card from the deck for comparison
        return self.deck.pop()

    async def start(self):
        # Starts the endgame phase by sending the initial embed
        await self.send_embed()

    async def send_embed(self):
        """
        Sends or updates the embed message displaying the current state of the endgame.
        """
        embed = discord.Embed(
            title="🚍 Busdriver Ride",
            description=f"**Busdriver:** {self.player.display_name}",
            color=discord.Color.red()
        )

        # Display the top cards (steps) with completed steps revealed
        card_display = ""
        for i, card in enumerate(self.top_cards):
            if i < self.highest_step + 1:
                card_display += f"{self.cog.bot.card_emojis.get(card)} "
            else:
                card_display += f"{self.cog.bot.card_emojis.get('back')} "
        embed.add_field(name="Top Cards", value=card_display, inline=False)

        # Display the cards drawn so far
        drawn_card_display = " ".join([self.cog.bot.card_emojis.get(card) for card in self.drawn_cards]) if self.drawn_cards else "None"
        embed.add_field(name="Drawn Cards", value=drawn_card_display, inline=False)

        # Add the status message if available
        if self.status_message:
            embed.add_field(name="Result", value=self.status_message, inline=False)

        # Display the current game stats
        embed.add_field(name="Tries", value=str(self.tries), inline=True)
        embed.add_field(name="Sips Drunk", value=str(self.sips), inline=True)
        embed.add_field(name="Step", value=str(self.current_step + 1), inline=True)

        # Check if the Busdriver has completed all steps
        if self.current_step >= self.max_steps:
            embed.description += "\n\n🎉 **You made it!**"
            rankings = Rankings(self.cog.bot, self.channel.guild.id)
            rankings.add_result(self.player.id, tries=self.tries, sips=self.sips)
            view = None  # No further interaction needed
            del self.cog.sessions[self.channel.guild.id]  # Remove the session
        else:
            # Provide the appropriate view for retrying or continuing
            if self.status_message:
                view = BusdriverRetryView(self)
            elif self.current_step >= self.max_steps:
                view = None
            else:
                view = BusdriverGameView(self)

        # Update or send the embed message
        await self.message.edit(embed=embed, view=view)

    async def handle_guess(self, interaction, guess):
        """
        Handles the Busdriver's guess for the current step.
        Determines if the guess is correct and updates the game state.
        """
        if interaction.user != self.player:
            # Only the Busdriver can make guesses
            await interaction.response.send_message("Only the Busdriver can play!", ephemeral=True)
            return

        if self.current_step >= self.max_steps:
            # End the game if all steps are completed
            return

        # Get the current top card and draw a new bottom card
        current_card = self.top_cards[self.current_step]
        self.bottom_card = self.draw_bottom_card()

        # Determine the values of the cards for comparison
        order = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
        prev_val = ''.join(filter(str.isdigit, current_card)) or current_card[0]
        new_val = ''.join(filter(str.isdigit, self.bottom_card)) or self.bottom_card[0]

        prev_value = order.index(prev_val)
        new_value = order.index(new_val)

        correct = False  # Whether the guess was correct
        penalty = self.current_step + 1  # Penalty for incorrect guesses

        # Determine if the guess is correct based on the comparison
        if guess == "equal":
            correct = prev_value == new_value
        elif guess == "higher":
            correct = new_value > prev_value
        elif guess == "lower":
            correct = new_value < prev_value

        self.drawn_cards.append(self.bottom_card)  # Add the drawn card to the list

        if correct:
            # Move to the next step if the guess is correct
            self.current_step += 1
            if self.current_step > self.highest_step:
                self.highest_step = self.current_step

            if self.current_step >= self.max_steps:
                # End the game if all steps are completed
                await self.send_embed()
                return
        else:
            # Update the status message and penalties for incorrect guesses
            self.status_message = f"❌ Wrong guess! Drink {penalty} sips."
            self.sips += penalty
            self.current_step = 0  # Reset to the first step
            self.tries += 1  # Increment the number of tries
            await self.send_embed()
            return

        await self.send_embed()

    async def save_score(self):
        # Delegates saving the Busdriver's score to the Rankings class.

        rankings = Rankings(self.cog.bot, self.channel.guild.id)
        rankings.add_result(self.player.id, tries=self.tries, sips=self.sips)

# Views und Buttons:

class BusdriverRetryView(discord.ui.View):
    # View for retrying the Busdriver endgame
    def __init__(self, game):
        super().__init__(timeout=None)
        self.game = game

    @discord.ui.button(label="🔄️ Try again", style=discord.ButtonStyle.green)
    async def retry(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Allow the Busdriver to retry the endgame
        if interaction.user != self.game.player:
            await interaction.response.send_message("Only the Busdriver can continue.", ephemeral=True)
            return

        await interaction.response.defer()
        self.game.status_message = ""  # Clear the status message
        self.game.current_step = 0  # Reset the current step
        self.game.drawn_cards = []  # Clear the drawn cards

        random.shuffle(self.game.deck)  # Shuffle the deck

        await self.game.send_embed()  # Update the embed with the new state

class BusdriverGameView(discord.ui.View):
    # View for the Busdriver endgame interface
    def __init__(self, game):
        super().__init__(timeout=None)
        self.game = game

    @discord.ui.button(emoji="🔼", style=discord.ButtonStyle.primary)
    async def higher(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Handle the "higher" guess
        await interaction.response.defer()
        await self.game.handle_guess(interaction, "higher")

    @discord.ui.button(emoji="🟰", style=discord.ButtonStyle.primary)
    async def equal(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Handle the "equal" guess
        await interaction.response.defer()
        await self.game.handle_guess(interaction, "equal")

    @discord.ui.button(emoji="🔽", style=discord.ButtonStyle.primary)
    async def lower(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Handle the "lower" guess
        await interaction.response.defer()
        await self.game.handle_guess(interaction, "lower")

### RANKINGS
class Rankings:
    # Handles ranking data for the Busdriver game
    def __init__(self, bot, guild_id):
        self.bot = bot
        os.makedirs(SAVE_FOLDER, exist_ok=True)  # Ensure the save folder exists

        # Paths for total and daily ranking files
        self.total_file = os.path.join(SAVE_FOLDER, f"{guild_id}_busdriver_scores.json")
        self.daily_file = os.path.join(SAVE_FOLDER, f"{guild_id}_busdriver_daily.json")

    def _load(self, filename):
        # Load ranking data from a file
        if not os.path.exists(filename):
            return {}
        with open(filename, "r") as f:
            return json.load(f)

    def _save(self, filename, data):
        # Save ranking data to a file
        with open(filename, "w") as f:
            json.dump(data, f)

    def _reset_daily_if_needed(self):
        # Reset the daily ranking file if it's a new day
        now = datetime.now()
        if now.hour >= 12:
            if not os.path.exists(self.daily_file):
                return
            mtime = datetime.fromtimestamp(os.path.getmtime(self.daily_file))
            if mtime.date() != now.date():
                self._save(self.daily_file, {})  # Reset daily file

    def add_result(self, user_id, tries, sips):
        # Add a player's result to the rankings
        user_id = str(user_id)

        self._reset_daily_if_needed()

        # Update total rankings
        total = self._load(self.total_file)
        if user_id not in total:
            total[user_id] = {"tries": 0, "sips": 0}
        total[user_id]["tries"] += tries
        total[user_id]["sips"] += sips
        self._save(self.total_file, total)

        # Update daily rankings
        daily = self._load(self.daily_file)
        if user_id not in daily:
            daily[user_id] = {"tries": 0, "sips": 0}
        daily[user_id]["tries"] += tries
        daily[user_id]["sips"] += sips
        self._save(self.daily_file, daily)

    def get_ranking(self, daily=False, limit=10):
        # Retrieve the ranking data (daily or total)
        filename = self.daily_file if daily else self.total_file
        data = self._load(filename)

        # Sort players by sips (descending) and tries (ascending)
        sorted_data = sorted(data.items(), key=lambda x: (-x[1]["sips"], x[1]["tries"]))

        # Format the ranking as a string
        result = []
        for i, (user_id, stats) in enumerate(sorted_data[:limit], 1):
            user = self.bot.get_user(int(user_id))
            name = user.display_name if user else f"User {user_id}"
            result.append(f"{i}. {name} - {stats['sips']} sips, {stats['tries']} tries")
        return "\n".join(result) if result else "No entries yet."

async def setup(bot):
    # Sets up the Busdriver cog.
    try:
        # Attempt to add the Color cog to the bot
        await bot.add_cog(Busdriver(bot))
        log.info("Busdriver cog successfully added to the bot.")
    except Exception as e:
        # Log and handle unexpected errors during setup
        log.error(f"Error setting up Busdriver cog: {e}")