# kinif

A minimal reader for **Wizard101's Gamebryo NIF model files** (versions ~20.x). It
extracts geometry — the vertex arrays of a model — which a caller can project to a 2D
footprint, build a hull from, or otherwise use. It deliberately skips everything else
(materials, textures, skinning, the node transform hierarchy).

It covers both geometry systems Wizard101 ships:

- the older `NiTriShapeData` / `NiTriStripsData` blocks (static props, FX), and
- the newer `NiMesh` / `NiDataStream` blocks (skinned characters — mobs and NPCs).

The format was reverse-engineered empirically and validated against real game NIFs
(versions 20.3.0.9, 20.2.0.8 and 20.6.0.0). The only dependency is `pyo3` for the
optional Python bindings.

## Python

Built as a Python extension with [maturin](https://github.com/PyO3/maturin):

```python
import kinif

# `data` is the raw bytes of a .nif file (e.g. read from a KingsIsle WAD)
verts = kinif.geometry_vertices(data)   # -> list[(x, y, z)] in model-local space
```

## Rust

```toml
[dependencies]
kinif = { git = "https://github.com/Deimos-Wizard101/kinif" }
```

```rust
let verts: Vec<[f32; 3]> = kinif::nif::geometry_vertices(&data)?;
```

Build the Rust library on its own (no Python) with `--no-default-features`.

## Origin

Written in-house for [Deimos](https://github.com/Deimos-Wizard101/Deimos-Wizard101),
where it powers collision-based teleporting by turning entity models into 2D collision
footprints. The old `pyffi` NIF library is long dead (Python 3.6, 2018), so this is a
from-scratch reader of just the geometry Deimos needs.

## License

GPL-3.0-only. See [LICENSE](LICENSE).
