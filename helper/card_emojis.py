# card_emojis.py
from logger import get_logger

log = get_logger(__name__)

class CardEmojiManager:
    # Manages card emojis for the bot, allowing easy access to custom emojis

    def __init__(self, bot):
        self.bot = bot  # Reference to the bot instance
        self.emoji_map = {}  # Dictionary to store emoji mappings

    async def load(self):
        # Loads all application emojis and maps them by their names
        try:
            emojis = await self.bot.fetch_application_emojis()  # Fetch all emojis for the bot
            self.emoji_map = {e.name.upper(): e for e in emojis}  # Map emojis by their uppercase names
            log.info("Successfully loaded card emojis.")
        except Exception as e:
            # Log and handle unexpected errors during emoji loading
            log.error(f"Error loading card emojis: {e}")

    def get(self, name: str) -> str:
        # Retrieves the emoji for a given card name
        # If the emoji is not found, returns a placeholder with the card name
        try:
            emoji = self.emoji_map.get(name.upper())  # Look up the emoji by its uppercase name
            return str(emoji) if emoji else f"[{name}]"  # Return the emoji or a placeholder
        except Exception as e:
            # Log and handle unexpected errors during emoji retrieval
            log.error(f"Error retrieving emoji for {name}: {e}")
            return f"[{name}]"