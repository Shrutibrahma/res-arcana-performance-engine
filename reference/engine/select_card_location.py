from __future__ import annotations

from enum import IntEnum


class SelectCardLocation(IntEnum):

    NONE = 0
    HAND = 1
    IN_PLAY = 2
    DISCARD = 3
    ANY_DISCARD = 4
    MONUMENT = 6
