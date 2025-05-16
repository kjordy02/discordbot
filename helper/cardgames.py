import random

def generate_standard_deck() -> list[str]:
    """Generates a shuffled standard 52-card deck.

    Returns:
        list[str]: A shuffled list of cards in the format "<value><suit>".
    """
    suits = ["H", "D", "S", "C"]
    values = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
    deck = [f"{v}{s}" for s in suits for v in values]
    random.shuffle(deck)
    return deck