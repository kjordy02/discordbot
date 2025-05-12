import discord
from discord.ext import commands
from discord import app_commands
import random

class KingsCup(commands.GroupCog, name="kingscup"):

    def __init__(self, bot):
        self.bot = bot
        self.sessions = {}

    class KingsCupSession:
        def __init__(self, host):
            self.host = host
            self.players = {}  # user_id -> member
            self.deck = self.create_deck()
            self.drawn_cards = []
            self.question_master = None
            self.rules = []
            self.mates = {}  # user_id -> mate_id
            self.kings_drawn = 0
            self.message = None

        def create_deck(self):
            suits = ["Hearts", "Diamonds", "Spades", "Clubs"]
            values = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
            return random.sample([f"{v} of {s}" for s in suits for v in values], 52)

    @app_commands.command(name="start", description="Start a Kings Cup game")
    async def start_game(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        if guild_id in self.sessions:
            await interaction.response.send_message("A Kings Cup game is already running!", ephemeral=True)
            return

        session = self.KingsCupSession(interaction.user)
        self.sessions[guild_id] = session

        view = KingsCupLobbyView(self, guild_id)
        embed = discord.Embed(title="👑 Kings Cup Lobby", description="Join the game before it starts!",
                              color=discord.Color.gold())
        session.message = await interaction.response.send_message(embed=embed, view=view)
        session.message = await interaction.original_response()

    @app_commands.command(name="rules", description="Show Kings Cup base card rules")
    async def show_rules(self, interaction: discord.Interaction):
        explanations = self.get_all_card_explanations()
        embed = discord.Embed(title="📜 Kings Cup Card Rules", color=discord.Color.orange())
        for value, text in explanations.items():
            embed.add_field(name=value, value=text, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    def get_all_card_explanations(self):
        return {
            "2": "You - Choose someone to drink.",
            "3": "Me - You drink.",
            "4": "All girls drink (if applicable).",
            "5": "Thumbmaster - Place your thumb visibly; last to copy drinks!",
            "6": "All guys drink (if applicable).",
            "7": "Heaven - Raise your hands! Last one drinks.",
            "8": "Mate - Pick a drinking partner for the rest of the game.",
            "9": "Rhyme - Start with a word, others must rhyme.",
            "10": "Category - Start a category, take turns until someone fails.",
            "J": "Rule - Choose to add or remove a rule.",
            "Q": "Question Master - Anyone who answers your question drinks!",
            "K": "King - Draw one of ten mystery cards.",
            "A": "Waterfall - Everyone drinks in order!"
        }

    async def update_game_embed(self, guild_id):
        session = self.sessions[guild_id]
        embed = discord.Embed(title="Kings Cup In Progress", color=discord.Color.dark_gold())
        drawn = ", ".join(session.drawn_cards[-5:]) if session.drawn_cards else "None yet"
        embed.add_field(name="Drawn Cards", value=drawn, inline=False)

        if session.question_master:
            qm = session.players.get(session.question_master)
            if qm:
                embed.set_footer(text=f"Question Master: {qm.display_name}")

        if session.rules:
            embed.add_field(name="📏 Rules", value="\n".join(session.rules[-3:]), inline=False)

        if session.mates:
            mate_lines = []
            for uid, mate_id in session.mates.items():
                user = session.players.get(uid)
                mate = session.players.get(mate_id)
                if user and mate:
                    mate_lines.append(f"{user.display_name} 🤝 {mate.display_name}")
            embed.add_field(name="👯 Mates", value="\n".join(mate_lines), inline=False)

        await session.message.edit(embed=embed, view=KingsCupGameView(self, guild_id))

    async def start_kingscup(self, guild_id, channel):
        session = self.sessions[guild_id]
        await session.message.edit(view=None)

        embed = discord.Embed(title="Kings Cup Started!", description="Game is running in voice/video chat.",
                              color=discord.Color.dark_gold())
        embed.add_field(name="Drawn Cards", value="None yet", inline=False)
        embed.set_footer(text="Use the button below to draw a card.")

        view = KingsCupGameView(self, guild_id)
        session.message = await channel.send(embed=embed, view=view)

    async def draw_card(self, guild_id, user):
        session = self.sessions[guild_id]

        if not session.deck:
            return discord.Embed(title="Deck is empty!", color=discord.Color.red())

        card = session.deck.pop()
        session.drawn_cards.append(card)
        value = card.split()[0]

        if value == "8":
            embed = discord.Embed(title="🃏 Mate!", description=f"{user.mention}, pick your drinking partner!",
                                  color=discord.Color.purple())
            return embed

        if value == "J":
            embed = discord.Embed(title="🃏 Jack!", description="Do you want to add or remove a rule?", color=discord.Color.blue())
            view = RuleActionView(self, guild_id)
            return embed, view

        if value == "K":
            session.kings_drawn += 1
            max_sips = [4, 6, 8, 10][min(session.kings_drawn - 1, 3)]
            sips = [f"-{random.randint(1, max_sips)} sips" for _ in range(9)]
            distribute = f"Distribute {max_sips} sips"
            all_options = sips + [distribute]
            random.shuffle(all_options)

            embed = discord.Embed(
                title=f"👑 King Challenge #{session.kings_drawn}",
                description=f"Pick one of the 10 hidden cards.\nMax value this round: {max_sips} sips",
                color=discord.Color.red()
            )
            for i, label in enumerate(all_options):
                embed.add_field(name=f"Card {i+1}", value=label, inline=True)
            embed.set_footer(text="Reveal and act via voice chat!")
            return embed

class KingsCupLobbyView(discord.ui.View):
    def __init__(self, cog, guild_id):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id

    @discord.ui.button(label="Join", style=discord.ButtonStyle.green)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = self.cog.sessions[self.guild_id]
        session.players[interaction.user.id] = interaction.user
        await self.cog.update_lobby(self.guild_id)
        await interaction.response.defer()

    @discord.ui.button(label="Leave", style=discord.ButtonStyle.red)
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = self.cog.sessions[self.guild_id]
        session.players.pop(interaction.user.id, None)
        await self.cog.update_lobby(self.guild_id)
        await interaction.response.defer()

    @discord.ui.button(label="Start Game", style=discord.ButtonStyle.blurple)
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = self.cog.sessions[self.guild_id]
        if interaction.user != session.host:
            await interaction.response.send_message("Only the host can start the game.", ephemeral=True)
            return
        if not session.players:
            await interaction.response.send_message("No players joined yet!", ephemeral=True)
            return
        self.stop()
        await self.cog.start_kingscup(self.guild_id, interaction.channel)

class KingsCupGameView(discord.ui.View):
    def __init__(self, cog, guild_id):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id

    @discord.ui.button(label="Draw Card", style=discord.ButtonStyle.primary)
    async def draw(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = await self.cog.draw_card(self.guild_id, interaction.user)
        await interaction.response.edit_message(embed=embed, view=self)

class RuleActionView(discord.ui.View):
    def __init__(self, cog, guild_id):
        super().__init__(timeout=60)
        self.cog = cog
        self.guild_id = guild_id

    @discord.ui.button(label="Add Rule", style=discord.ButtonStyle.green)
    async def add_rule(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RuleInputModal(self.cog, self.guild_id, add=True))

    @discord.ui.button(label="Remove Rule", style=discord.ButtonStyle.red)
    async def remove_rule(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RuleInputModal(self.cog, self.guild_id, add=False))

class RuleInputModal(discord.ui.Modal, title="Modify Rule"):
    def __init__(self, cog, guild_id, add=True):
        super().__init__()
        self.cog = cog
        self.guild_id = guild_id
        self.add = add
        label = "Enter new rule" if add else "Enter exact rule to remove"
        self.rule_input = discord.ui.TextInput(label=label, style=discord.TextStyle.paragraph, required=True)
        self.add_item(self.rule_input)

    async def on_submit(self, interaction: discord.Interaction):
        session = self.cog.sessions[self.guild_id]
        rule_text = self.rule_input.value.strip()
        if self.add:
            session.rules.append(rule_text)
            await interaction.response.send_message(f"✅ Rule added:\n**{rule_text}**", ephemeral=True)
        else:
            if rule_text in session.rules:
                session.rules.remove(rule_text)
                await interaction.response.send_message(f"🗑️ Rule removed:\n**{rule_text}**", ephemeral=True)
            else:
                await interaction.response.send_message("⚠️ Rule not found.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(KingsCup(bot))