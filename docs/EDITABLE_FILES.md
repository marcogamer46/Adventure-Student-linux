# Your implementation files

Work in the six supplied modules under `src/student`: `character.py`, `artifact.py`, `enemy.py`, `terrain_generator.py`, `level_generator.py`, and `controller.py`. Preserve each required class, constructor, property, and method signature. You may add ordinary student helper modules inside this package and use the public API and permitted standard library. Keep framework, renderer, setup, art, and prepared public inputs unchanged.

Character, Artifact, and Enemy retain their supplied entity data and expose the required read-only properties. TerrainGenerator returns floor geometry. LevelGenerator uses its injected terrain generator and returns the initial world. AgentController reads the current snapshot and returns one action. Read the [objects introduction](../GUIDE.html#meet-the-objects) and [exact API reference](guide/api-reference.html) as needed.

A ready-made controller scenario requires Character, AgentController, and the entity classes actually present. Both generators may remain TODO. Terrain generation requires TerrainGenerator only. Level generation requires LevelGenerator and the selected terrain provider, plus any student entities your assembly constructs; AgentController can remain TODO. Using provided terrain isolates level assembly. Using your terrain tests their dependency.

Save edits in your IDE before selecting Run solution, Run again, Generate terrain, or Generate level in the workbench. The workbench creates a fresh owned attempt and saves its output automatically. Replay controls inspect saved frames without executing your source. Return to [README](../README.md) for setup and [the seven-case guide](../GUIDE.html) for practice.
