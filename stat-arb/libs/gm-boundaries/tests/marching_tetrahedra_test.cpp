// Reference tests for marching_tetrahedra: the standard way to validate
// an isosurface extractor is to run it on an ANALYTIC shape (ADR-011's
// own stated testing approach for the boundary mesh) - a sphere, here -
// and confirm every emitted vertex actually lies on that shape within a
// tolerance set by the grid resolution.

#include <gm-boundaries/marching_tetrahedra.hpp>

#include <catch2/catch_test_macros.hpp>

#include <cmath>

using gm::boundaries::marching_tetrahedra;
using gm::boundaries::Mesh;

TEST_CASE("extracts a sphere: every vertex lies on the sphere within grid tolerance",
          "[marching_tetrahedra]") {
    double radius = 1.0;
    auto field = [](double x, double y, double z) {
        // Field = 1/(1+r) so isovalue 0.5 is exactly r=1 (avoids the
        // isovalue sitting at a field extremum, which some grid points
        // could hit exactly and create degenerate zero-length edges).
        return 1.0 / (1.0 + std::sqrt(x * x + y * y + z * z));
    };

    int resolution = 24;
    auto result = marching_tetrahedra(field, {-2.0, -2.0, -2.0}, {2.0, 2.0, 2.0}, resolution, 0.5);
    REQUIRE(result.has_value());
    REQUIRE(result->vertices.size() > 0);
    REQUIRE(result->triangles.size() > 0);

    double cell_size = 4.0 / static_cast<double>(resolution);
    // A vertex is a linear interpolation along one grid edge, so it can
    // be off the true sphere by up to roughly the local curvature error
    // over one cell - a small multiple of cell_size is the right
    // tolerance, not an exact match.
    double tolerance = 1.5 * cell_size;

    double max_error = 0.0;
    for (const auto& v : result->vertices) {
        double r = std::sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]);
        max_error = std::max(max_error, std::abs(r - radius));
    }
    CHECK(max_error < tolerance);
}

TEST_CASE("a field entirely above the isovalue produces an empty mesh", "[marching_tetrahedra]") {
    auto field = [](double, double, double) { return 100.0; };
    auto result = marching_tetrahedra(field, {0, 0, 0}, {1, 1, 1}, 4, 0.5);
    REQUIRE(result.has_value());
    CHECK(result->vertices.empty());
    CHECK(result->triangles.empty());
}

TEST_CASE("a field entirely below the isovalue produces an empty mesh", "[marching_tetrahedra]") {
    auto field = [](double, double, double) { return -100.0; };
    auto result = marching_tetrahedra(field, {0, 0, 0}, {1, 1, 1}, 4, 0.5);
    REQUIRE(result.has_value());
    CHECK(result->vertices.empty());
    CHECK(result->triangles.empty());
}

TEST_CASE("every triangle is non-degenerate (nonzero area)", "[marching_tetrahedra]") {
    auto field = [](double x, double y, double z) { return -(x * x + y * y + z * z); };
    auto result = marching_tetrahedra(field, {-1.5, -1.5, -1.5}, {1.5, 1.5, 1.5}, 10, -1.0);
    REQUIRE(result.has_value());
    REQUIRE(result->triangles.empty() == false);

    for (const auto& tri : result->triangles) {
        const auto& a = result->vertices[tri[0]];
        const auto& b = result->vertices[tri[1]];
        const auto& c = result->vertices[tri[2]];
        double ux = b[0] - a[0], uy = b[1] - a[1], uz = b[2] - a[2];
        double vx = c[0] - a[0], vy = c[1] - a[1], vz = c[2] - a[2];
        // Cross product magnitude = 2x triangle area.
        double cx = uy * vz - uz * vy;
        double cy = uz * vx - ux * vz;
        double cz = ux * vy - uy * vx;
        double area2 = std::sqrt(cx * cx + cy * cy + cz * cz);
        CHECK(area2 > 1e-12);
    }
}

TEST_CASE("invalid resolution is rejected", "[marching_tetrahedra]") {
    auto field = [](double, double, double) { return 0.0; };
    auto result = marching_tetrahedra(field, {0, 0, 0}, {1, 1, 1}, 0, 0.5);
    REQUIRE_FALSE(result.has_value());
    CHECK(result.error().code == gm::ErrorCode::kInvalidArgument);
}

TEST_CASE("inverted bounds are rejected", "[marching_tetrahedra]") {
    auto field = [](double, double, double) { return 0.0; };
    auto result = marching_tetrahedra(field, {1, 1, 1}, {0, 0, 0}, 4, 0.5);
    REQUIRE_FALSE(result.has_value());
    CHECK(result.error().code == gm::ErrorCode::kInvalidArgument);
}
