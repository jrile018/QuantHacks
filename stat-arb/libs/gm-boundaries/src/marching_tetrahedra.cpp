#include <gm-boundaries/marching_tetrahedra.hpp>

#include <cmath>

namespace gm::boundaries {

namespace {

using Point = std::array<double, 3>;

Point interpolate_edge(const Point& pa, double va, const Point& pb, double vb, double isovalue) {
    // va != vb is guaranteed by the caller (only called on edges that
    // actually cross the isovalue, i.e. va and vb are on opposite
    // sides), so this division is always well-defined.
    double t = (isovalue - va) / (vb - va);
    return {pa[0] + t * (pb[0] - pa[0]), pa[1] + t * (pb[1] - pa[1]), pa[2] + t * (pb[2] - pa[2])};
}

std::uint32_t add_vertex(Mesh& mesh, const Point& p) {
    mesh.vertices.push_back(p);
    return static_cast<std::uint32_t>(mesh.vertices.size() - 1);
}

/// Processes one tetrahedron (4 corner points + scalar values) and
/// appends its contribution to the isosurface. Case analysis derived
/// directly from first principles, not recalled from a published table:
/// classify each corner as "above" (value >= isovalue) or "below", and
/// handle by how many corners are above (0..4 - a tetrahedron has only
/// 4 corners, so there are only 5 cases, each independently reasoned
/// about below):
///
///   0 above (all below) or 4 above (all above): the isosurface does
///     not pass through this tetrahedron at all - nothing to emit.
///
///   1 above, 3 below: the surface cuts off the single "above" corner.
///     It crosses exactly the 3 edges connecting that corner to each of
///     the 3 "below" corners (an edge only crosses the isovalue when
///     its two endpoints are on opposite sides) - one triangle, at
///     those 3 interpolated crossing points.
///
///   3 above, 1 below: the exact mirror of the 1-above case - the
///     single "below" corner is cut off, via the 3 edges from it to
///     each "above" corner. Same shape as the 1-above case, just
///     carved from the opposite side.
///
///   2 above, 2 below: every one of the 2 "above" corners connects to
///     every one of the 2 "below" corners - that's 2*2 = 4 edges, all
///     of which cross the isovalue (no edge exists between two corners
///     on the SAME side, so those two edges of the tetrahedron are
///     irrelevant here). Four crossing points form a quadrilateral,
///     split into 2 triangles.
void process_tetrahedron(Mesh& mesh, const std::array<Point, 4>& corners,
                          const std::array<double, 4>& values, double isovalue) {
    std::array<bool, 4> above{};
    int above_count = 0;
    for (int i = 0; i < 4; ++i) {
        above[static_cast<std::size_t>(i)] = values[static_cast<std::size_t>(i)] >= isovalue;
        if (above[static_cast<std::size_t>(i)]) ++above_count;
    }

    if (above_count == 0 || above_count == 4) return;  // no crossing in this tet

    if (above_count == 1 || above_count == 3) {
        // Find the single odd-one-out corner (the lone "above" when
        // above_count==1, or the lone "below" when above_count==3).
        bool odd_is_above = (above_count == 1);
        int odd = -1;
        for (int i = 0; i < 4; ++i) {
            if (above[static_cast<std::size_t>(i)] == odd_is_above) {
                odd = i;
                break;
            }
        }
        std::array<std::uint32_t, 3> tri_indices{};
        int slot = 0;
        for (int i = 0; i < 4; ++i) {
            if (i == odd) continue;
            Point crossing = interpolate_edge(corners[static_cast<std::size_t>(odd)],
                                               values[static_cast<std::size_t>(odd)],
                                               corners[static_cast<std::size_t>(i)],
                                               values[static_cast<std::size_t>(i)], isovalue);
            tri_indices[static_cast<std::size_t>(slot++)] = add_vertex(mesh, crossing);
        }
        mesh.triangles.push_back(tri_indices);
        return;
    }

    // above_count == 2: gather the 2 "above" and 2 "below" corner
    // indices, then interpolate all 4 above-to-below edges.
    std::array<int, 2> above_idx{}, below_idx{};
    int ai = 0, bi = 0;
    for (int i = 0; i < 4; ++i) {
        if (above[static_cast<std::size_t>(i)]) above_idx[static_cast<std::size_t>(ai++)] = i;
        else below_idx[static_cast<std::size_t>(bi++)] = i;
    }

    // Quad corners in order a0-b0-a1-b1 (a walk around the quad: each
    // consecutive pair shares one tetrahedron edge), split into two
    // triangles sharing the a0-a1 diagonal.
    auto cross = [&](int a, int b) {
        return interpolate_edge(corners[static_cast<std::size_t>(a)], values[static_cast<std::size_t>(a)],
                                 corners[static_cast<std::size_t>(b)], values[static_cast<std::size_t>(b)],
                                 isovalue);
    };
    std::uint32_t q00 = add_vertex(mesh, cross(above_idx[0], below_idx[0]));
    std::uint32_t q01 = add_vertex(mesh, cross(above_idx[0], below_idx[1]));
    std::uint32_t q10 = add_vertex(mesh, cross(above_idx[1], below_idx[0]));
    std::uint32_t q11 = add_vertex(mesh, cross(above_idx[1], below_idx[1]));
    mesh.triangles.push_back({q00, q01, q10});
    mesh.triangles.push_back({q01, q11, q10});
}

} // namespace

Result<Mesh> marching_tetrahedra(const std::function<double(double, double, double)>& scalar_field,
                                  const std::array<double, 3>& min_bound,
                                  const std::array<double, 3>& max_bound, int resolution,
                                  double isovalue) {
    if (resolution < 1) {
        return tl::unexpected(
            gm::Error::make(gm::ErrorCode::kInvalidArgument, "resolution must be >= 1"));
    }
    for (int d = 0; d < 3; ++d) {
        if (!(max_bound[static_cast<std::size_t>(d)] > min_bound[static_cast<std::size_t>(d)])) {
            return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument,
                                                   "max_bound must exceed min_bound in every axis",
                                                   "axis " + std::to_string(d)));
        }
    }

    int gp = resolution + 1;  // grid points per axis

    // Cache every grid-point evaluation once (each is reused by up to 8
    // adjacent cells' worth of tetrahedra) rather than re-evaluating
    // scalar_field per tetrahedron corner.
    std::vector<double> values(static_cast<std::size_t>(gp) * static_cast<std::size_t>(gp) *
                                static_cast<std::size_t>(gp));
    std::vector<Point> points(values.size());
    auto index_of = [gp](int i, int j, int k) {
        return (static_cast<std::size_t>(i) * static_cast<std::size_t>(gp) +
                static_cast<std::size_t>(j)) *
                   static_cast<std::size_t>(gp) +
               static_cast<std::size_t>(k);
    };

    for (int i = 0; i < gp; ++i) {
        double x = min_bound[0] + (max_bound[0] - min_bound[0]) * static_cast<double>(i) /
                                       static_cast<double>(resolution);
        for (int j = 0; j < gp; ++j) {
            double y = min_bound[1] + (max_bound[1] - min_bound[1]) * static_cast<double>(j) /
                                           static_cast<double>(resolution);
            for (int k = 0; k < gp; ++k) {
                double z = min_bound[2] + (max_bound[2] - min_bound[2]) * static_cast<double>(k) /
                                               static_cast<double>(resolution);
                std::size_t idx = index_of(i, j, k);
                points[idx] = {x, y, z};
                values[idx] = scalar_field(x, y, z);
            }
        }
    }

    // Standard 6-tetrahedra decomposition of a cube sharing the main
    // diagonal c0(0,0,0)-c6(1,1,1); the other 6 corners form a ring
    // around that diagonal, and each tetrahedron is the diagonal plus
    // one edge of that ring. c0..c7 indexed by (dx,dy,dz) bits below.
    static constexpr std::array<std::array<int, 3>, 8> kCubeOffsets = {{
        {0, 0, 0}, {1, 0, 0}, {1, 1, 0}, {0, 1, 0}, {0, 0, 1}, {1, 0, 1}, {1, 1, 1}, {0, 1, 1},
    }};
    static constexpr std::array<std::array<int, 4>, 6> kTetsOfCube = {{
        {0, 1, 2, 6}, {0, 2, 3, 6}, {0, 3, 7, 6}, {0, 7, 4, 6}, {0, 4, 5, 6}, {0, 5, 1, 6},
    }};

    Mesh mesh;
    for (int i = 0; i < resolution; ++i) {
        for (int j = 0; j < resolution; ++j) {
            for (int k = 0; k < resolution; ++k) {
                std::array<Point, 8> cube_points;
                std::array<double, 8> cube_values;
                for (int c = 0; c < 8; ++c) {
                    const auto& off = kCubeOffsets[static_cast<std::size_t>(c)];
                    std::size_t idx = index_of(i + off[0], j + off[1], k + off[2]);
                    cube_points[static_cast<std::size_t>(c)] = points[idx];
                    cube_values[static_cast<std::size_t>(c)] = values[idx];
                }

                for (const auto& tet : kTetsOfCube) {
                    std::array<Point, 4> tp;
                    std::array<double, 4> tv;
                    for (int v = 0; v < 4; ++v) {
                        tp[static_cast<std::size_t>(v)] =
                            cube_points[static_cast<std::size_t>(tet[static_cast<std::size_t>(v)])];
                        tv[static_cast<std::size_t>(v)] =
                            cube_values[static_cast<std::size_t>(tet[static_cast<std::size_t>(v)])];
                    }
                    process_tetrahedron(mesh, tp, tv, isovalue);
                }
            }
        }
    }

    return mesh;
}

} // namespace gm::boundaries
