//! Minimal reader for Wizard101's Gamebryo NIF model files (versions ~20.x).
//!
//! We only need geometry: the vertex arrays of every `NiTriShapeData` /
//! `NiTriStripsData` block, which the Python side projects to a 2D footprint for
//! entity collision. We deliberately skip everything else (materials, textures,
//! skinning, the node transform hierarchy) — the footprint is built from raw
//! vertices and then placed at the entity's world location, matching how the
//! reference (QuestWhiz) approximates entity collisions.
//!
//! Header layout validated against real W101 NIFs (versions 20.3.0.9 and
//! 20.6.0.0): both place `num_block_types` immediately after `num_blocks`, so a
//! single layout covers the files the game ships.

use std::fmt;

#[derive(Debug)]
pub enum NifError {
    BadHeader,
    Truncated,
    Overrun,
}

impl fmt::Display for NifError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            NifError::BadHeader => write!(f, "not a recognizable NIF header"),
            NifError::Truncated => write!(f, "unexpected end of NIF data"),
            NifError::Overrun => write!(f, "NIF block table overruns the file"),
        }
    }
}

impl std::error::Error for NifError {}

/// Little-endian cursor over the NIF byte buffer.
struct Reader<'a> {
    d: &'a [u8],
    pos: usize,
}

impl<'a> Reader<'a> {
    fn new(d: &'a [u8], pos: usize) -> Self {
        Self { d, pos }
    }

    fn take(&mut self, n: usize) -> Result<&'a [u8], NifError> {
        let end = self.pos.checked_add(n).ok_or(NifError::Truncated)?;
        if end > self.d.len() {
            return Err(NifError::Truncated);
        }
        let s = &self.d[self.pos..end];
        self.pos = end;
        Ok(s)
    }

    fn u8(&mut self) -> Result<u8, NifError> {
        Ok(self.take(1)?[0])
    }

    fn u16(&mut self) -> Result<u16, NifError> {
        let b = self.take(2)?;
        Ok(u16::from_le_bytes([b[0], b[1]]))
    }

    fn u32(&mut self) -> Result<u32, NifError> {
        let b = self.take(4)?;
        Ok(u32::from_le_bytes([b[0], b[1], b[2], b[3]]))
    }

    fn i32(&mut self) -> Result<i32, NifError> {
        Ok(self.u32()? as i32)
    }

    fn f32(&mut self) -> Result<f32, NifError> {
        let b = self.take(4)?;
        Ok(f32::from_le_bytes([b[0], b[1], b[2], b[3]]))
    }

    fn skip(&mut self, n: usize) -> Result<(), NifError> {
        self.take(n)?;
        Ok(())
    }
}

const GEOMETRY_BLOCKS: [&[u8]; 2] = [b"NiTriShapeData", b"NiTriStripsData"];
const DATASTREAM_PREFIX: &[u8] = b"NiDataStream";

/// Convert an IEEE-754 half (binary16) to f32.
fn half_to_f32(h: u16) -> f32 {
    let sign = (h >> 15) & 1;
    let exp = (h >> 10) & 0x1f;
    let mant = h & 0x3ff;
    let val = if exp == 0 {
        (mant as f32) * 2f32.powi(-24) // zero / subnormal
    } else if exp == 0x1f {
        if mant == 0 { f32::INFINITY } else { f32::NAN }
    } else {
        (1.0 + (mant as f32) / 1024.0) * 2f32.powi(exp as i32 - 15)
    };
    if sign == 1 { -val } else { val }
}

/// A NiDataStream block type name is `NiDataStream\x01<usage>\x01<access>`; pull the
/// usage out (1 = per-vertex attribute data, which is where positions live).
fn datastream_usage(name: &[u8]) -> Option<u32> {
    let rest = name.strip_prefix(DATASTREAM_PREFIX)?;
    let field = rest.split(|&b| b == 0x01).find(|s| !s.is_empty())?;
    std::str::from_utf8(field).ok()?.parse().ok()
}

/// Read a NiMesh position stream (a usage=1 NiDataStream of float32×3 or float16×3)
/// and append its vertices to `out`. Normal/tangent streams share the same format,
/// so we keep a float3 stream only when its vectors are mostly *not* unit length —
/// positions are model-space, whereas normals/tangents are unit vectors.
fn collect_datastream_positions(data: &[u8], block_start: usize, out: &mut Vec<[f32; 3]>) -> Result<(), NifError> {
    let mut r = Reader::new(data, block_start);
    let num_bytes = r.u32()? as usize;
    let _cloning_behavior = r.u32()?;
    let num_regions = r.u32()? as usize;
    r.skip(num_regions * 8)?; // each region is { start_byte: u32, num_bytes: u32 }
    let num_components = r.u32()? as usize;
    if num_components != 1 {
        return Ok(()); // interleaved streams aren't plain position buffers; skip
    }
    let format = r.u32()?;
    let component_count = (format >> 16) & 0xff;
    let bytes_per_component = (format >> 8) & 0xff;
    if component_count != 3 || (bytes_per_component != 4 && bytes_per_component != 2) {
        return Ok(()); // not a float3 stream (e.g. UVs, colors, indices)
    }
    let stride = (component_count * bytes_per_component) as usize;
    let count = num_bytes / stride;

    let mut verts = Vec::with_capacity(count);
    for _ in 0..count {
        let v = if bytes_per_component == 4 {
            [r.f32()?, r.f32()?, r.f32()?]
        } else {
            [half_to_f32(r.u16()?), half_to_f32(r.u16()?), half_to_f32(r.u16()?)]
        };
        verts.push(v);
    }

    if verts.is_empty() {
        return Ok(());
    }
    let unit = verts
        .iter()
        .filter(|v| {
            let m = (v[0] * v[0] + v[1] * v[1] + v[2] * v[2]).sqrt();
            (0.9..=1.1).contains(&m)
        })
        .count();
    if (unit as f32) / (verts.len() as f32) < 0.5 {
        out.extend(verts);
    }
    Ok(())
}

/// Parse a NIF file and return every geometry vertex (model-local space) as
/// `[x, y, z]`. Covers both W101 geometry systems: the older
/// `NiTriShapeData`/`NiTriStripsData` (static props, FX) and the newer
/// `NiMesh`/`NiDataStream` (skinned characters — mobs and NPCs).
pub fn geometry_vertices(data: &[u8]) -> Result<Vec<[f32; 3]>, NifError> {
    // The header is a text line ("Gamebryo File Format, Version ...") ended by \n.
    let nl = data
        .iter()
        .position(|&b| b == 0x0a)
        .ok_or(NifError::BadHeader)?;

    let mut r = Reader::new(data, nl + 1);
    let _version = r.u32()?;
    let _endian = r.u8()?;
    let _user_version = r.u32()?;
    let num_blocks = r.u32()? as usize;

    // Block type table.
    let num_block_types = r.u16()? as usize;
    let mut types: Vec<&[u8]> = Vec::with_capacity(num_block_types);
    for _ in 0..num_block_types {
        let len = r.u32()? as usize;
        types.push(r.take(len)?);
    }

    // Per-block: which type, and how many bytes the block occupies.
    let mut block_type_index = Vec::with_capacity(num_blocks);
    for _ in 0..num_blocks {
        block_type_index.push(r.u16()? as usize);
    }
    let mut block_sizes = Vec::with_capacity(num_blocks);
    for _ in 0..num_blocks {
        block_sizes.push(r.u32()? as usize);
    }

    // String table, then group table — we don't need either, just skip past them.
    let num_strings = r.u32()? as usize;
    let _max_string_length = r.u32()?;
    for _ in 0..num_strings {
        let len = r.u32()? as usize;
        r.skip(len)?;
    }
    let num_groups = r.u32()? as usize;
    r.skip(num_groups * 4)?;

    // Blocks follow back-to-back; block_sizes tells us where each one starts.
    let mut out = Vec::new();
    let mut block_start = r.pos;
    for i in 0..num_blocks {
        let size = block_sizes[i];
        let tname = types.get(block_type_index[i]).copied().unwrap_or(b"");
        if GEOMETRY_BLOCKS.contains(&tname) {
            // NiGeometryData prefix (W101 20.x): group_id(i32), num_vertices(u16),
            // keep_flags(u8), compress_flags(u8), has_vertices(u8), then the verts.
            let mut br = Reader::new(data, block_start);
            let _group_id = br.i32()?;
            let num_vertices = br.u16()? as usize;
            let _keep_flags = br.u8()?;
            let _compress_flags = br.u8()?;
            let has_vertices = br.u8()?;
            if has_vertices != 0 {
                out.reserve(num_vertices);
                for _ in 0..num_vertices {
                    let x = br.f32()?;
                    let y = br.f32()?;
                    let z = br.f32()?;
                    out.push([x, y, z]);
                }
            }
        } else if tname.starts_with(DATASTREAM_PREFIX) && datastream_usage(tname) == Some(1) {
            collect_datastream_positions(data, block_start, &mut out)?;
        }
        block_start = block_start.checked_add(size).ok_or(NifError::Overrun)?;
        if block_start > data.len() {
            return Err(NifError::Overrun);
        }
    }

    Ok(out)
}
