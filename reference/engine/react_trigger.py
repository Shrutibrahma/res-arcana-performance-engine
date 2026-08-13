from __future__ import annotations

from enum import IntEnum


class ReactTrigger(IntEnum):

    NONE = 0
    DAMAGE = 1
    VICTORY_CHECK = 2
    DRAGON_ATTACK = 7
