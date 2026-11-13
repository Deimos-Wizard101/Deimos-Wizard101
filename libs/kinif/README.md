# kinif

A minimal reader for **Wizard101's Gamebryo NIF model files**. It deliberately skips everything but the model mesh for use in collision detetion..

It covers both geometry systems Wizard101 ships:
- the older `NiTriShapeData` / `NiTriStripsData` blocks (static props, FX), and
- the newer `NiMesh` / `NiDataStream` blocks (skinned characters — mobs and NPCs).

## License

GPL-3.0-only. See [LICENSE](LICENSE).
