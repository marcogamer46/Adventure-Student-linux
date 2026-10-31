"""TODO: select one public action from each immutable world observation."""
from src.api import WorldAction, WorldSnapshot


class AgentController:
    """A new controller is constructed for each run; arrival still needs EXIT."""

    def __init__(self) -> None:
        raise NotImplementedError("TODO AgentController: implement constructor and choose_action")

    def choose_action(self, state: WorldSnapshot, agent_id: str) -> WorldAction:
        # Return an exact WorldAction; illegal responses are rejected, not changed to WAIT.
        raise NotImplementedError("TODO AgentController.choose_action")
