from __future__ import annotations

from enum import IntEnum


class TargetOption(IntEnum):

    TAKE = 0
    DECLINE = 1
    PAY = 2
    TURN = 3
    LIFE = 4
    ANY = 5
    DECK = 6
    DISCARD = 7
