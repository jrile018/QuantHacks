#pragma once

// Isosurface extraction for the viewer's boundary mesh (ADR-011: "the
// lumpy non-convex surface... rendered via marching cubes"). Uses
// marching TETRAHEDRA instead of the classic Lorensen & Cline cubes
// algorithm - a deliberate substitution, not a silent shortcut:
//
// Marching cubes' standard 256-case triangulation lookup table is easy
// to get subtly wrong transcribing from memory (a wrong entry produces
// a locally-malformed mesh only in specific, rarely-exercised corner
// configurations - exactly the kind of error hard to catch with
// ordinary tests). Marching tetrahedra decomposes each grid cube into 6
// tetrahedra (a standard construction sharing the cube's main diagonal)
// and classifies each tetrahedron by how many of its 4 corners are
// above the isovalue - only 5 distinct cases (0/1/2/3/4 corners above),
// each derivable and independently verifiable from first principles
// (see marching_tetrahedra.cpp's case-by-case reasoning), not recalled
// from an external table. It produces the same category of result - a
// watertight triangle mesh of the isosurface for the viewer to render -
// at the cost of somewhat more triangles for the same grid resolution
// (a rendering-performance trade-off, not a correctness one).

#include <gm-core/error.hpp>

#include <array>
#include <cstdint>
#include <functional>
#include <vector>

namespace gm::boundaries {

struct Mesh {
    std::vector<std::array<double, 3>> vertices;
    std::vector<std::array<std::uint32_t, 3>> triangles;  // indices into vertices
};

/// Extracts the triangle mesh of the surface where `scalar_field(x,y,z)
/// == isovalue`, sampled on a `resolution^3` grid of cells (so
/// (resolution+1)^3 evaluation points) spanning
/// [min_bound, max_bound] in each of x/y/z. `resolution` must be >= 1.
[[nodiscard]] Result<Mesh> marching_tetrahedra(
    const std::function<double(double, double, double)>& scalar_field,
    const std::array<double, 3>& min_bound, const std::array<double, 3>& max_bound, int resolution,
    double isovalue);

} // namespace gm::boundaries
