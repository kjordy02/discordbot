import logging
from logging.handlers import RotatingFileHandler

LOG_FILE = 'app.log'
LOG_LEVEL = logging.INFO
DISCORD_LOG_LEVEL = logging.DEBUG
DISCORD_HTTP_LOG_LEVEL = logging.INFO

# Format und Datum
LOG_FORMAT = '[{asctime}] [{levelname:<8}] {name}: {message}'
DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

# Hauptlogger konfigurieren
root_logger = logging.getLogger()
root_logger.setLevel(LOG_LEVEL)

# Rotierender FileHandler
file_handler = RotatingFileHandler(
    filename=LOG_FILE,
    encoding='utf-8',
    maxBytes=32 * 1024 * 1024,  # 32 MiB
    backupCount=5  # max 5 Logdateien
)
formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT, style='{')
file_handler.setFormatter(formatter)
root_logger.addHandler(file_handler)

# Konfiguriere Discord-spezifisches Logging
discord_logger = logging.getLogger('discord')
discord_logger.setLevel(DISCORD_LOG_LEVEL)
http_logger = logging.getLogger('discord.http')
http_logger.setLevel(DISCORD_HTTP_LOG_LEVEL)

def get_logger(name: str) -> logging.Logger:
    """Gibt einen Logger zurück, der in jedem Modul verwendet werden kann."""
    return logging.getLogger(name)