import logging

# Setup Logger
logging.basicConfig(
    level=logging.INFO,  # Default Level (kann auf DEBUG geändert werden für Tests)
    format='[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def get_logger(name):
    """Gibt einen Logger zurück, den man in jedem Modul verwenden kann."""
    return logging.getLogger(name)