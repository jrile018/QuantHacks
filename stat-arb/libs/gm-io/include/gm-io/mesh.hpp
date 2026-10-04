#pragma once

// The `.gmmesh` boundary-surface format (ADR-017, ADR.md §8.2:
// "boundary meshes are a compact versioned binary (header + vertex/index
// buffers)").
//
// WHY THIS LIVES IN gm-io AND NOT NEXT TO THE MESH GENERATOR
// ----------------------------------------------------------
// `gm::boundaries::Mesh` is produced by marching_tetrahedra, but
// `gm-boundaries-lib` does not link `gm-io`, and `gm-view` - the consumer -
// links `gm-io` but not `gm-boundaries`. Putting the format here, over a
// plain struct with no Eigen or estimator dependencies, is what lets the
// producer and the consumer share it without either growing a dependency on
// the other. `apps/gm-boundaries` links both and converts at that one point.
//
// WHAT WAS ACTUALLY MISSING
// -------------------------
// A comment in apps/gm-boundaries/main.cpp described mesh export as "opt-in
// via boundaries.write_meshes, defaulting OFF". No such config key was ever
// read, no writer existed, and the manifest line reporting it was a
// hardcoded string. So the surface ADR-011 specifies - the lumpy non-convex
// envelope around the point cloud, which is the whole visual point of the
// viewer - could not be produced at all, and gm-view had no code to draw one
// even if it could. This file is the first of the three pieces.
//
// FORMAT (all little-endian, which every target platform is; see the
// static_assert in mesh.cpp)
// -------------------------------------------------------------------
//   offset  size  field
//   0       6     magic, the ASCII bytes "GMMESH"
//   6       2     uint16 version (currently 1)
//   8       8     uint64 vertex count
//   16      8     uint64 triangle count
//   24      24*V  vertices, three float64 each (x, y, z)
//   ...     12*T  triangles, three uint32 each, indices into the vertices
//
// float64 rather than float32 for vertices: these are run artifacts under
// ADR-017's immutability rule, not just display buffers, and a lossy write
// would make a mesh something you cannot reason about numerically later. The
// cost is file size, which is managed by choosing which frames to export
// rather than by quietly degrading every one of them.

#include <gm-core/error.hpp>

#include <array>
#include <cstdint>
#include <filesystem>
#include <vector>

namespace gm::io {

/// A triangle mesh, structurally identical to `gm::boundaries::Mesh` but
/// free of that library's dependencies so both sides can share it.
struct MeshData {
    std::vector<std::array<double, 3>> vertices;
    std::vector<std::array<std::uint32_t, 3>> triangles; ///< indices into `vertices`
};

/// Current format version written by write_gmmesh.
inline constexpr std::uint16_t kGmMeshVersion = 1;

/// Writes `mesh` to `path`, creating parent directories if needed.
///
/// Rejects a mesh whose triangles reference vertices that do not exist:
/// writing one would produce an artifact that crashes its consumer, and a
/// corrupt file on disk is worse than a failed write.
[[nodiscard]] gm::VoidResult write_gmmesh(const MeshData& mesh,
                                           const std::filesystem::path& path);

/// Reads a `.gmmesh` file.
///
/// Validates, in order: the magic bytes, the version (refusing anything it
/// does not understand, per ADR-017), that the file is exactly the length its
/// header implies, and that every triangle index is in range. The length
/// check happens BEFORE any allocation sized from the header, so a corrupt or
/// hostile file cannot induce a huge allocation.
[[nodiscard]] Result<MeshData> read_gmmesh(const std::filesystem::path& path);

} // namespace gm::io
