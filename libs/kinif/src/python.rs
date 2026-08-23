use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

use crate::nif;

/// Return every geometry vertex `(x, y, z)` from a NIF file's triangle data
/// blocks, in model-local space. Raises ValueError on malformed data.
#[pyfunction]
fn geometry_vertices(py: Python<'_>, data: Vec<u8>) -> PyResult<Vec<(f32, f32, f32)>> {
    let verts = py
        .allow_threads(|| nif::geometry_vertices(&data))
        .map_err(|e| PyValueError::new_err(e.to_string()))?;
    Ok(verts.into_iter().map(|v| (v[0], v[1], v[2])).collect())
}

#[pymodule]
fn kinif(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(geometry_vertices, m)?)?;
    Ok(())
}
