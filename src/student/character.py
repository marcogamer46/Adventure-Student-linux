"""TODO: implement your character's immutable, canonical public identity."""
from src.api import CharacterDefinition


class Character:
    """Character(agent_id); expose a read-only str agent_id property."""

    def __init__(self, agent_id: str) -> None:
        # Validate using public canonical values and retain your own state.
        raise NotImplementedError("TODO Character: implement __init__ and agent_id")

    @property
    def agent_id(self) -> str:
        raise NotImplementedError("TODO Character.agent_id")
