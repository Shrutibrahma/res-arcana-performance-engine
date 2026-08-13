from __future__ import annotations

from enum import IntEnum


class CollectDecision(IntEnum):
    PAY_COST = 0
    PAY_TURN = 1
    DECLINE_COST = 2
    TAKE_STORED = 3
    LEAVE_STORED = 4
