#pragma once

// Minimal OpenGL 3.3 core helpers for gm-view: shader compilation and a
// single VAO/VBO point-cloud renderer. The manifold view (ADR-018) is,
// at its rendering core, exactly this - N colored points in 3D space -
// so one small, direct wrapper is clearer than a general-purpose scene
// graph this project doesn't otherwise need.

#include <gm-core/error.hpp>
#include <gm-io/mesh.hpp>

#include <cstdint>
#include <string>
#include <vector>

#include "camera.hpp"

namespace gm::view {

struct PointVertex {
    float x, y, z;
    float r, g, b;
};

/// Compiles and links a vertex+fragment shader pair. Returns the
/// program id, or an error with the GL-reported compile/link log on
/// failure - never silently continues with a program id of 0.
[[nodiscard]] Result<std::uint32_t> compile_shader_program(const std::string& vertex_src,
                                                             const std::string& fragment_src);

/// Owns one VAO/VBO pair for rendering a point cloud with per-vertex
/// color and a uniform point size. Vertex data is re-uploaded whenever
/// the caller switches frames (ADR-018's time scrubber) via upload().
class PointCloudRenderer {
public:
    [[nodiscard]] static Result<PointCloudRenderer> create();
    ~PointCloudRenderer();

    PointCloudRenderer(const PointCloudRenderer&) = delete;
    PointCloudRenderer& operator=(const PointCloudRenderer&) = delete;
    PointCloudRenderer(PointCloudRenderer&& other) noexcept;
    PointCloudRenderer& operator=(PointCloudRenderer&& other) noexcept;

    void upload(const std::vector<PointVertex>& points);
    void draw(const Mat4& mvp, float point_size) const;

private:
    PointCloudRenderer() = default;
    void release();

    std::uint32_t program_ = 0;
    std::uint32_t vao_ = 0;
    std::uint32_t vbo_ = 0;
    std::uint32_t mvp_uniform_loc_ = 0;
    std::uint32_t point_size_uniform_loc_ = 0;
    std::size_t vertex_count_ = 0;
};

/// Owns one VAO/VBO/EBO for rendering a boundary surface (ADR-011's
/// "lumpy non-convex surface") as a wireframe around the point cloud.
///
/// Wireframe rather than a shaded solid, deliberately: the points this
/// surface encloses are the whole subject, and a filled envelope hides
/// every one of them. Drawn via glPolygonMode(GL_LINE) over the triangle
/// index buffer rather than by building a separate edge buffer - the
/// same triangles, one draw call, and no second representation of the
/// mesh that could drift out of step with the first.
class MeshRenderer {
public:
    [[nodiscard]] static Result<MeshRenderer> create();
    ~MeshRenderer();

    MeshRenderer(const MeshRenderer&) = delete;
    MeshRenderer& operator=(const MeshRenderer&) = delete;
    MeshRenderer(MeshRenderer&& other) noexcept;
    MeshRenderer& operator=(MeshRenderer&& other) noexcept;

    /// Uploads `mesh`, converting its float64 vertices to float32 for the
    /// GPU. The narrowing is a rendering concern only - the artifact on
    /// disk stays float64 (see gm-io/mesh.hpp).
    void upload(const gm::io::MeshData& mesh);

    /// Drops any uploaded geometry, so a frame with no surface on disk
    /// draws nothing rather than leaving the previous frame's surface on
    /// screen - which would be a quietly misleading picture.
    void clear();

    [[nodiscard]] bool empty() const noexcept { return index_count_ == 0; }

    void draw(const Mat4& mvp, float r, float g, float b, float a) const;

private:
    MeshRenderer() = default;
    void release();

    std::uint32_t program_ = 0;
    std::uint32_t vao_ = 0;
    std::uint32_t vbo_ = 0;
    std::uint32_t ebo_ = 0;
    std::uint32_t mvp_uniform_loc_ = 0;
    std::uint32_t color_uniform_loc_ = 0;
    std::size_t index_count_ = 0;
};

} // namespace gm::view
