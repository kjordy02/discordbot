# card_emojis.py

class CardEmojiManager:
    def __init__(self, bot):
        self.bot = bot
        self.emoji_map = {}

    async def load(self):
        emojis = await self.bot.fetch_application_emojis()
        self.emoji_map = {e.name.upper(): e for e in emojis}

    def get(self, name: str) -> str:
        emoji = self.emoji_map.get(name.upper())
        return str(emoji) if emoji else f"[{name}]"