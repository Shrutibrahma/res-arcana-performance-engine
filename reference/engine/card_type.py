from enum import IntEnum, IntFlag


class CardType(IntEnum):
    NONE = 0
    DRAGON = 1
    CREATURE = 2


class CardTypeMask(IntFlag):

    NONE = 0
    DRAGON = 1 << CardType.DRAGON
    CREATURE = 1 << CardType.CREATURE


class EntityFlag(IntFlag):

    NONE = 0
    CANNOT_BE_FREE_PLACED = 1 << 0
    CANNOT_BE_DISCARDED = 1 << 1


def type_mask(*types: CardType) -> int:
    result = 0
    for t in types:
        result |= 1 << t
    return result
