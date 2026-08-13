from __future__ import annotations

from dataclasses import dataclass, field

from .action_types import PlayerId
from .pool import Pool


@dataclass
class PlayerState:

    pid: PlayerId

    pool: Pool = field(default_factory=Pool)

    has_passed: bool = False
    has_first_player_token: bool = False

    is_active: bool = False
