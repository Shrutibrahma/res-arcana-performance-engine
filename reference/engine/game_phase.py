from enum import IntEnum


class GamePhase(IntEnum):

    SETUP_GAME = 0
    SETUP_CHOOSE_MAGES = 1
    SETUP_CHOOSE_ITEMS = 2
    COLLECT = 3
    ACTIONS = 4
    VICTORY_CHECK = 5
    GAME_OVER = 6
