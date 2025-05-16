import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import random
from helper.stats_formatter import StatsFormatter as SF
from logger import get_logger

log = get_logger(__name__)

class HorseRace(commands.GroupCog, name="horserace"):
    """Main class for the Horse Race game cog."""

    def __init__(self, bot):
        """Initializes the HorseRace cog with the bot instance."""
        self.bot = bot
        self.sessions = {}  # Active race sessions by guild ID
        self.pending_joins = {}  # Pending join requests by guild ID
        self.session_id = None  # For tracking DB session ID

    @commands.Cog.listener()
    async def on_ready(self):
        """Event listener triggered when the bot is ready."""
        log.info("HorseRace module loaded and ready.")

    class RaceSession:
        """Represents a single race session."""
        def __init__(self, host):
            """Initializes a new race session."""
            self.host = host  # The user who started the race
            self.players = {}  # Mapping of user_id -> {"member": member, "bet": 0, "horse": None}
            self.started = False  # Indicates if the race has started
            self.deck = []  # The shuffled deck of cards
            self.progress = {"H": 0, "D": 0, "S": 0, "C": 0}  # Progress of each horse
            self.blockades = []  # Blockade cards
            self.finished = False  # Indicates if the race has finished
            self.winner = None  # The winning horse
            self.reached_levels = {"H": set(), "D": set(), "S": set(), "C": set()}  # Levels reached by each horse
            self.lobby_view = None  # The lobby view for the session

        def generate_deck(self):
            """Generates a shuffled deck and selects blockade cards."""
            suits = ["H", "D", "S", "C"]
            values = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
            full_deck = [f"{v}{s}" for s in suits for v in values]

            # Remove Aces (starting horses)
            for suit in suits:
                full_deck.remove(f"A{suit}")

            # Randomly select blockade cards
            blockade_cards = random.sample(full_deck, 4)

            # Remove blockade cards from the deck
            for card in blockade_cards:
                full_deck.remove(card)

            # Shuffle the remaining deck
            random.shuffle(full_deck)

            return full_deck, blockade_cards

    @app_commands.command(name="start", description="Start a horse race drinking game")
    async def start_race(self, interaction: discord.Interaction):
        """Starts a new horse race session."""
        guild_id = interaction.guild.id
        if guild_id in self.sessions:
            await interaction.response.send_message("A race is already running!", ephemeral=True)
            log.warning(f"Attempted to start a race in guild {interaction.guild.name} while one is already running.")
            return

        session = self.RaceSession(interaction.user)  # Create a new race session
        self.sessions[guild_id] = session

        view = PregameView(self, guild_id)  # Create the pregame lobby view
        session.lobby_view = view
        embed = discord.Embed(title="🐎 Horse Race Lobby", description="Players can join!", color=discord.Color.green())
        await interaction.response.send_message(embed=embed, view=view)
        session.message = await interaction.original_response()
        log.info(f"Started a new race in guild {interaction.guild.name} by {interaction.user.display_name}.")

    @app_commands.command(name="stats", description="Show Horserace rankings")
    async def stats(self, interaction: discord.Interaction):
        """Displays Horserace rankings."""
        await interaction.response.defer()
        db = self.bot.db
        gid = interaction.guild.id

        stats = {
            "🏆 All Time (Global)": {
                "🍻 Most Drunk": SF.format_top_list(db.get_horserace_main_ranking("sips_drunk", "global")),
                "🎯 Most Given": SF.format_top_list(db.get_horserace_main_ranking("sips_given", "global"))
            },
            "🏘️ All Time (This Server)": {
                "🍻 Most Drunk": SF.format_top_list(db.get_horserace_main_ranking("sips_drunk", "server", gid)),
                "🎯 Most Given": SF.format_top_list(db.get_horserace_main_ranking("sips_given", "server", gid))
            },
            "🌙 Today (This Server)": {
                "🍻 Most Drunk": SF.format_top_list(db.get_horserace_main_ranking("sips_drunk", "server", gid, today=True)),
                "🎯 Most Given": SF.format_top_list(db.get_horserace_main_ranking("sips_given", "server", gid, today=True))
            }
        }

        embed = SF.build_embed("🐎 Horserace Stats", stats)
        await interaction.followup.send(embed=embed)

    async def update_lobby(self, guild_id):
        """Updates the lobby message with the current list of players."""
        session = self.sessions[guild_id]

        desc = ""
        for p in session.players.values():
            suit = p["horse"]
            emoji = self.bot.card_emojis.get(f"A{suit}", "❓")
            desc += f"{p['member'].mention} {emoji} {p['bet']} sips\n"

        if not desc:
            desc = "*No one yet*"

        embed = discord.Embed(title="🐎 Horse Race Lobby", description=desc, color=discord.Color.green())
        try:
            await session.message.edit(embed=embed, view=PregameView(self, guild_id))
            log.info(f"Updated lobby for guild {guild_id}.")
        except Exception as e:
            log.error(f"Failed to update lobby for guild {guild_id}: {e}")

    async def start_race_game(self, guild_id, channel):
        """Starts the actual race game."""
        session = self.sessions[guild_id]

        try:
            await session.message.edit(view=None)
        except Exception as e:
            log.error(f"Failed to clear lobby view for guild {guild_id}: {e}")

        session.started = True
        # Direkt nach: session.started = True
        db = self.bot.db
        server_db_id = db.get_or_create_server(guild_id)
        session.session_id = db.create_game_session(server_db_id, "horserace")

        # Save bets as drunk sips
        for player_id, pdata in session.players.items():
            user_db_id = db.get_or_create_user(player_id)
            db.insert_horserace_stat(session.session_id, user_db_id, sips_drunk=pdata["bet"], sips_given=0)

        # Initialize 
        session.deck, blockade_cards = session.generate_deck()
        session.blockade_targets = [card[-1] for card in blockade_cards]
        session.blockades = ["HIDDEN"] * 4
        session.blockade_revealed = [False] * 4

        try:
            await session.message.edit(embed=self.build_race_embed(session), view=None)
        except Exception as e:
            log.error(f"Failed to initialize race embed for guild {guild_id}: {e}")

        while not session.finished:
            await asyncio.sleep(2)

            if len(session.deck) == 0:
                # Log a warning if the deck is exhausted
                log.warning(f"Deck exhausted in guild {guild_id}. Ending race.")
                break

            card = session.deck.pop()  # Draw the next card from the deck
            suit = card[-1]  # Extract the suit of the card
            value = card[:-1]  # Extract the value of the card

            session.progress[suit] += 1  # Increment the progress of the horse
            session.reached_levels[suit].add(session.progress[suit])  # Track the levels reached by the horse

            if session.progress[suit] >= 5:
                # End the race if a horse reaches the finish line
                session.finished = True
                session.winner = suit
                log.info(f"Race finished in guild {guild_id}. Winner: {suit}.")
                break

            for blockade_index in range(4):
                if not session.blockade_revealed[blockade_index]:
                    blockade_level = blockade_index + 1

                    # Check if all horses have reached the blockade level
                    if all(blockade_level in levels for levels in session.reached_levels.values()):
                        target = session.blockade_targets[blockade_index]
                        session.blockades[blockade_index] = self.bot.card_emojis.get(f"{target}", "❓")
                        session.blockade_revealed[blockade_index] = True

                        try:
                            # Update the embed to reveal the blockade
                            await session.message.edit(embed=self.build_race_embed(session, reset=target, last_card=card), view=None)
                            await asyncio.sleep(2)
                            session.progress[target] = 0  # Reset the progress of the blocked horse
                            await session.message.edit(embed=self.build_race_embed(session, reset=target, last_card=card), view=None)
                        except Exception as e:
                            log.error(f"Failed to update blockade for guild {guild_id}: {e}")
                        break

            try:
                # Update the embed with the latest race progress
                await session.message.edit(embed=self.build_race_embed(session, last_card=card), view=None)
            except Exception as e:
                log.error(f"Failed to update race progress for guild {guild_id}: {e}")

        # Finish the race and display the results
        await self.finish_race(guild_id, channel)

    def build_race_embed(self, session, reset=None, last_card=None):
        """Builds the embed message displaying the current state of the race."""
        embed = discord.Embed(title="🐎 Horse Race in Progress...", color=discord.Color.blue())

        bets = []
        # Add player bets to the embed
        for p in session.players.values():
            suit = p["horse"]
            emoji = self.bot.card_emojis.get(f"A{suit}", "❓")
            bets.append(f"{p['member'].mention} ({emoji} - {p['bet']} sips)")
        embed.add_field(name="💰 Bets", value="\n".join(bets), inline=False)

        if last_card:
            # Display the last drawn card
            emoji = self.bot.card_emojis.get(last_card, "❓")
            embed.add_field(name="🃏 Last Card", value=emoji, inline=False)

        # Build the blockade line
        blockade_line = "⬛"
        for blockade_card in session.blockades:
            blockade_line += blockade_card if blockade_card != "HIDDEN" else self.bot.card_emojis.get("back", "❓")
        blockade_line += "👑"
        embed.add_field(name="⠀", value=blockade_line, inline=False)

        # Add progress for each horse
        suit_names = {"H": "Hearts", "D": "Diamonds", "S": "Spades", "C": "Clubs"}
        for suit in ["H", "D", "S", "C"]:
            if session.progress[suit] == 0:
                # Display the starting position of the horse
                line = self.bot.card_emojis.get(f"A{suit}", "❓")
            else:
                # Display an empty space for progress
                line = "⬜"

            for i in range(1, 6):
                if session.progress[suit] == i:
                    # Show the horse's current position
                    line += self.bot.card_emojis.get(f"A{suit}", "❓")
                elif i == 5:
                    # Show the finish line
                    line += "👑" if session.finished and suit == session.winner else "🟩"
                else:
                    # Show empty spaces for remaining progress
                    line += "⬜"

            # Add the horse's progress line to the embed
            embed.add_field(name="⠀", value=line, inline=False)

        return embed

    async def finish_race(self, guild_id, channel):
        """Handles the end of the race."""
        session = self.sessions[guild_id]
        embed = self.build_race_embed(session)

        # Prepare the result text
        result_text = f"🎉 **{self.bot.card_emojis.get(f'A{session.winner}', '❓')} {session.winner} has won!**\n\n"
        winners = []

        # Identify players who bet on the winning horse
        for p in session.players.values():
            if p["horse"] == session.winner:
                # update the database with the winnings
                db = self.bot.db
                user_id = db.get_or_create_user(p["member"].id)
                db.update_horserace_given(session.session_id, user_id, sips=p["bet"] * 2)
                # Add the player to the winners list
                winners.append((p["member"], p["bet"] * 2))

        if winners:
            # Add winners to the result text
            result_text += "\n".join([f"{m.mention} can give out **{sips} sips**!" for m, sips in winners])
        else:
            # Add a message if no one bet on the winning horse
            result_text += "Unfortunately, no one bet on the winning horse."

        # Add the result text to the embed
        embed.add_field(name="🏆 Result", value=result_text, inline=False)
        try:
            # Update the message with the final results
            await session.message.edit(embed=embed, view=None)
            log.info(f"Race finished in guild {guild_id}. Results sent.")
        except Exception as e:
            # Log an error if the results could not be sent
            log.error(f"Failed to send race results for guild {guild_id}: {e}")
        del self.sessions[guild_id]  # Remove the session after the race ends

# --------------------- VIEWS ----------------------------

class PregameView(discord.ui.View):
    """View for the pregame lobby where players can join or leave."""
    def __init__(self, cog, guild_id):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id

    @discord.ui.button(label="Join", style=discord.ButtonStyle.green)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle a player joining the lobby."""
        session = self.cog.sessions[self.guild_id]

        if interaction.user.id in session.players:
            # Prevent duplicate joins
            await interaction.response.send_message("You are already in the lobby!", ephemeral=True)
            return

        if self.guild_id not in self.cog.pending_joins:
            # Initialize pending joins for the guild
            self.cog.pending_joins[self.guild_id] = {}

        # Add the player to the pending joins
        self.cog.pending_joins[self.guild_id][interaction.user.id] = {"horse": None, "bet": None}

        # Send a message prompting the player to choose their horse and bet
        await interaction.response.send_message(
            "Please choose your horse and bet to join the lobby:",
            view=PlayerJoinSelectionView(self.cog, self.guild_id, interaction.user.id),
            ephemeral=True
        )

    @discord.ui.button(label="Leave", style=discord.ButtonStyle.red)
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle a player leaving the lobby."""
        session = self.cog.sessions[self.guild_id]
        if interaction.user.id in session.players:
            # Remove the player from the session
            del session.players[interaction.user.id]
        await self.cog.update_lobby(self.guild_id)  # Update the lobby
        await interaction.response.defer()

    @discord.ui.button(label="Start", style=discord.ButtonStyle.blurple)
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle starting the race."""
        session = self.cog.sessions[self.guild_id]

        if interaction.user != session.host:
            # Only the host can start the race
            await interaction.response.send_message("Only the host can start!", ephemeral=True)
            return

        if not session.players:
            # Ensure there are players in the lobby
            await interaction.response.send_message("There are no players in the lobby!", ephemeral=True)
            return

        session.lobby_view.stop()  # Stop the lobby view
        await session.message.edit(view=None)  # Clear the lobby view
        await self.cog.start_race_game(self.guild_id, interaction.channel)  # Start the race

class PlayerJoinSelectionView(discord.ui.View):
    """View for selecting a horse and bet when joining the lobby."""
    def __init__(self, cog, guild_id, player_id):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id
        self.player_id = player_id

        # Add dropdowns for selecting a horse and bet
        self.add_item(PlayerHorseDropdown(cog, guild_id, player_id, locked=False))
        self.add_item(PlayerBetDropdown(cog, guild_id, player_id, locked=False))
        self.add_item(PlayerJoinConfirmButton(cog, guild_id, player_id))

class PlayerJoinConfirmButton(discord.ui.Button):
    """Button for confirming the player's join selection."""
    def __init__(self, cog, guild_id, player_id):
        super().__init__(label="Join", style=discord.ButtonStyle.success)
        self.cog = cog
        self.guild_id = guild_id
        self.player_id = player_id

    async def callback(self, interaction: discord.Interaction):
        """Handle the player's join confirmation."""
        session = self.cog.sessions[self.guild_id]

        guild_pending = self.cog.pending_joins.get(self.guild_id, {})
        pending = guild_pending.get(self.player_id)

        if not pending:
            # Handle expired join sessions
            await interaction.response.send_message("Your join session has expired. Please try again.", ephemeral=True)
            return

        if not pending["horse"] or not pending["bet"]:
            # Ensure the player has selected both a horse and a bet
            await interaction.response.send_message("Please choose your horse and bet first!", ephemeral=True)
            return

        # Add the player to the session
        session.players[self.player_id] = {
            "member": interaction.user,
            "bet": pending["bet"],
            "horse": pending["horse"],
            "locked": True
        }

        # Remove the player from pending joins
        del self.cog.pending_joins[self.guild_id][self.player_id]
        await self.cog.update_lobby(self.guild_id)  # Update the lobby

        self.view.stop()  # Stop the join selection view
        await interaction.response.defer(ephemeral=True)

class PlayerHorseDropdown(discord.ui.Select):
    """Dropdown for selecting a horse."""
    def __init__(self, cog, guild_id, player_id, locked):
        session = cog.sessions[guild_id]
        player_data = session.players.get(player_id, {})
        current = player_data.get("horse", None)

        # Define the dropdown options for horses
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
        """Handle the horse selection."""
        pending = self.cog.pending_joins[self.guild_id][self.player_id]
        pending["horse"] = self.values[0]
        await interaction.response.defer()

class PlayerBetDropdown(discord.ui.Select):
    """Dropdown for selecting a bet."""
    def __init__(self, cog, guild_id, player_id, locked):
        session = cog.sessions[guild_id]
        player_data = session.players.get(player_id, {})
        current = player_data.get("bet", None)

        # Define the dropdown options for bets
        options = [discord.SelectOption(label=f"{i} sips", value=str(i), default=(current == i)) for i in range(1, 11)]
        super().__init__(placeholder="Choose sips", min_values=1, max_values=1, options=options, disabled=locked)

        self.cog = cog
        self.guild_id = guild_id
        self.player_id = player_id

    async def callback(self, interaction: discord.Interaction):
        """Handle the bet selection."""
        pending = self.cog.pending_joins[self.guild_id][self.player_id]
        pending["bet"] = int(self.values[0])
        await interaction.response.defer()

# --------------------- SETUP ----------------------------

async def setup(bot):
    """Sets up the HorseRace cog."""
    try:
        # Attempt to add the HorseRace cog to the bot
        await bot.add_cog(HorseRace(bot))
        log.info("HorseRace cog successfully added to the bot.")
    except Exception as e:
        # Log and handle unexpected errors during setup
        log.error(f"Error setting up HorseRace cog: {e}")