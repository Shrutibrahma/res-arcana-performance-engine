from typing import NewType

EntityId = NewType("EntityId", int)

PlayerId = NewType("PlayerId", int)

UNOWNED = PlayerId(5)

SENTINEL_EID = EntityId(255)
