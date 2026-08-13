from __future__ import annotations

from enum import IntEnum


class CardLocation(IntEnum):

    OUT_OF_GAME = 0
    AVAILABLE = 1
    MONUMENT_DECK = 2
    DECK = 3
    HAND = 4
    IN_PLAY = 5
    DISCARD = 6
    BEING_CHOSEN = 7
