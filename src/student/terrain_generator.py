"""TODO: generate canonical terrain deterministically from specification and seed."""
from src.api import Terrain, TerrainGenerationSpec


class TerrainGenerator:
    """Keep state local; identical inputs must also agree across fresh instances."""

    def __init__(self) -> None:
        raise NotImplementedError("TODO TerrainGenerator: implement constructor and generate_terrain")

    def generate_terrain(self, specification: TerrainGenerationSpec, seed: int) -> Terrain:
        # This workbench accepts only its documented public introductory family.
        raise NotImplementedError("TODO TerrainGenerator.generate_terrain")
