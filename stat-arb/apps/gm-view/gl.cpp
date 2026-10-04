#include "gl.hpp"

#include <glad/glad.h>

#include <cstddef>
#include <utility>
#include <vector>

namespace gm::view {

namespace {

constexpr const char* kVertexShaderSrc = R"glsl(
#version 330 core
layout(location = 0) in vec3 aPos;
layout(location = 1) in vec3 aColor;
uniform mat4 uMVP;
uniform float uPointSize;
out vec3 vColor;
void main() {
    gl_Position = uMVP * vec4(aPos, 1.0);
    gl_PointSize = uPointSize;
    vColor = aColor;
}
)glsl";

constexpr const char* kFragmentShaderSrc = R"glsl(
#version 330 core
in vec3 vColor;
out vec4 FragColor;
void main() {
    // Round point sprites: discard the corners of the square point quad.
    vec2 coord = gl_PointCoord - vec2(0.5);
    if (dot(coord, coord) > 0.25) discard;
    FragColor = vec4(vColor, 1.0);
}
)glsl";

Result<std::uint32_t> compile_stage(GLenum stage, const std::string& src) {
    std::uint32_t shader = glCreateShader(stage);
    const char* src_ptr = src.c_str();
    glShaderSource(shader, 1, &src_ptr, nullptr);
    glCompileShader(shader);

    GLint success = 0;
    glGetShaderiv(shader, GL_COMPILE_STATUS, &success);
    if (!success) {
        char log[1024];
        GLsizei len = 0;
        glGetShaderInfoLog(shader, sizeof(log), &len, log);
        glDeleteShader(shader);
        std::string detail(log, static_cast<std::size_t>(len));
        // glGetShaderInfoLog itself respects the buffer size (no
        // overrun risk), but a real GLSL error - especially with macro
        // expansion - can genuinely exceed 1024 bytes; say so rather
        // than silently handing back a log that just stops mid-message.
        if (static_cast<std::size_t>(len) >= sizeof(log) - 1) {
            detail += "\n[...shader error log truncated at 1024 bytes...]";
        }
        return tl::unexpected(
            gm::Error::make(gm::ErrorCode::kNumericFailure, "GLSL shader compilation failed", detail));
    }
    return shader;
}

} // namespace

Result<std::uint32_t> compile_shader_program(const std::string& vertex_src,
                                              const std::string& fragment_src) {
    auto vs = compile_stage(GL_VERTEX_SHADER, vertex_src);
    if (!vs) return tl::unexpected(vs.error());
    auto fs = compile_stage(GL_FRAGMENT_SHADER, fragment_src);
    if (!fs) {
        glDeleteShader(*vs);
        return tl::unexpected(fs.error());
    }

    std::uint32_t program = glCreateProgram();
    glAttachShader(program, *vs);
    glAttachShader(program, *fs);
    glLinkProgram(program);

    glDeleteShader(*vs);
    glDeleteShader(*fs);

    GLint success = 0;
    glGetProgramiv(program, GL_LINK_STATUS, &success);
    if (!success) {
        char log[1024];
        GLsizei len = 0;
        glGetProgramInfoLog(program, sizeof(log), &len, log);
        glDeleteProgram(program);
        std::string detail(log, static_cast<std::size_t>(len));
        if (static_cast<std::size_t>(len) >= sizeof(log) - 1) {
            detail += "\n[...program link log truncated at 1024 bytes...]";
        }
        return tl::unexpected(
            gm::Error::make(gm::ErrorCode::kNumericFailure, "GLSL shader program link failed", detail));
    }
    return program;
}

Result<PointCloudRenderer> PointCloudRenderer::create() {
    auto program = compile_shader_program(kVertexShaderSrc, kFragmentShaderSrc);
    if (!program) return tl::unexpected(program.error());

    PointCloudRenderer renderer;
    renderer.program_ = *program;

    glGenVertexArrays(1, &renderer.vao_);
    glGenBuffers(1, &renderer.vbo_);

    glBindVertexArray(renderer.vao_);
    glBindBuffer(GL_ARRAY_BUFFER, renderer.vbo_);
    glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, sizeof(PointVertex),
                           reinterpret_cast<void*>(offsetof(PointVertex, x)));
    glEnableVertexAttribArray(0);
    glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, sizeof(PointVertex),
                           reinterpret_cast<void*>(offsetof(PointVertex, r)));
    glEnableVertexAttribArray(1);
    glBindVertexArray(0);

    renderer.mvp_uniform_loc_ =
        static_cast<std::uint32_t>(glGetUniformLocation(renderer.program_, "uMVP"));
    renderer.point_size_uniform_loc_ =
        static_cast<std::uint32_t>(glGetUniformLocation(renderer.program_, "uPointSize"));

    return renderer;
}

PointCloudRenderer::~PointCloudRenderer() { release(); }

void PointCloudRenderer::release() {
    if (vbo_) glDeleteBuffers(1, &vbo_);
    if (vao_) glDeleteVertexArrays(1, &vao_);
    if (program_) glDeleteProgram(program_);
    vbo_ = vao_ = program_ = 0;
}

PointCloudRenderer::PointCloudRenderer(PointCloudRenderer&& other) noexcept
    : program_(other.program_),
      vao_(other.vao_),
      vbo_(other.vbo_),
      mvp_uniform_loc_(other.mvp_uniform_loc_),
      point_size_uniform_loc_(other.point_size_uniform_loc_),
      vertex_count_(other.vertex_count_) {
    other.program_ = other.vao_ = other.vbo_ = 0;
    other.vertex_count_ = 0;
}

PointCloudRenderer& PointCloudRenderer::operator=(PointCloudRenderer&& other) noexcept {
    if (this != &other) {
        release();
        program_ = other.program_;
        vao_ = other.vao_;
        vbo_ = other.vbo_;
        mvp_uniform_loc_ = other.mvp_uniform_loc_;
        point_size_uniform_loc_ = other.point_size_uniform_loc_;
        vertex_count_ = other.vertex_count_;
        other.program_ = other.vao_ = other.vbo_ = 0;
        other.vertex_count_ = 0;
    }
    return *this;
}

void PointCloudRenderer::upload(const std::vector<PointVertex>& points) {
    vertex_count_ = points.size();
    glBindBuffer(GL_ARRAY_BUFFER, vbo_);
    glBufferData(GL_ARRAY_BUFFER,
                 static_cast<GLsizeiptr>(points.size() * sizeof(PointVertex)), points.data(),
                 GL_DYNAMIC_DRAW);
}

void PointCloudRenderer::draw(const Mat4& mvp, float point_size) const {
    if (vertex_count_ == 0) return;
    glUseProgram(program_);
    glUniformMatrix4fv(static_cast<GLint>(mvp_uniform_loc_), 1, GL_FALSE, mvp.data());
    glUniform1f(static_cast<GLint>(point_size_uniform_loc_), point_size);
    glEnable(GL_PROGRAM_POINT_SIZE);
    glBindVertexArray(vao_);
    glDrawArrays(GL_POINTS, 0, static_cast<GLsizei>(vertex_count_));
    glBindVertexArray(0);
}


// ---------------------------------------------------------------------------
// MeshRenderer
// ---------------------------------------------------------------------------

namespace {

constexpr const char* kMeshVertexShaderSrc = R"glsl(
#version 330 core
layout(location = 0) in vec3 aPos;
uniform mat4 uMVP;
void main() {
    gl_Position = uMVP * vec4(aPos, 1.0);
}
)glsl";

constexpr const char* kMeshFragmentShaderSrc = R"glsl(
#version 330 core
uniform vec4 uColor;
out vec4 FragColor;
void main() {
    FragColor = uColor;
}
)glsl";

} // namespace

Result<MeshRenderer> MeshRenderer::create() {
    auto program = compile_shader_program(kMeshVertexShaderSrc, kMeshFragmentShaderSrc);
    if (!program) return tl::unexpected(program.error());

    MeshRenderer renderer;
    renderer.program_ = *program;
    glGenVertexArrays(1, &renderer.vao_);
    glGenBuffers(1, &renderer.vbo_);
    glGenBuffers(1, &renderer.ebo_);

    glBindVertexArray(renderer.vao_);
    glBindBuffer(GL_ARRAY_BUFFER, renderer.vbo_);
    glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 3 * sizeof(float), nullptr);
    glEnableVertexAttribArray(0);
    // The element buffer binding is part of VAO state, so binding it here
    // means draw() does not have to rebind it every frame.
    glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, renderer.ebo_);
    glBindVertexArray(0);

    renderer.mvp_uniform_loc_ =
        static_cast<std::uint32_t>(glGetUniformLocation(renderer.program_, "uMVP"));
    renderer.color_uniform_loc_ =
        static_cast<std::uint32_t>(glGetUniformLocation(renderer.program_, "uColor"));
    return renderer;
}

MeshRenderer::~MeshRenderer() { release(); }

void MeshRenderer::release() {
    if (ebo_ != 0) glDeleteBuffers(1, &ebo_);
    if (vbo_ != 0) glDeleteBuffers(1, &vbo_);
    if (vao_ != 0) glDeleteVertexArrays(1, &vao_);
    if (program_ != 0) glDeleteProgram(program_);
    program_ = vao_ = vbo_ = ebo_ = 0;
    index_count_ = 0;
}

MeshRenderer::MeshRenderer(MeshRenderer&& other) noexcept { *this = std::move(other); }

MeshRenderer& MeshRenderer::operator=(MeshRenderer&& other) noexcept {
    if (this != &other) {
        release();
        program_ = other.program_;
        vao_ = other.vao_;
        vbo_ = other.vbo_;
        ebo_ = other.ebo_;
        mvp_uniform_loc_ = other.mvp_uniform_loc_;
        color_uniform_loc_ = other.color_uniform_loc_;
        index_count_ = other.index_count_;
        other.program_ = other.vao_ = other.vbo_ = other.ebo_ = 0;
        other.index_count_ = 0;
    }
    return *this;
}

void MeshRenderer::upload(const gm::io::MeshData& mesh) {
    std::vector<float> positions;
    positions.reserve(mesh.vertices.size() * 3);
    for (const auto& v : mesh.vertices) {
        positions.push_back(static_cast<float>(v[0]));
        positions.push_back(static_cast<float>(v[1]));
        positions.push_back(static_cast<float>(v[2]));
    }
    std::vector<std::uint32_t> indices;
    indices.reserve(mesh.triangles.size() * 3);
    for (const auto& t : mesh.triangles) {
        indices.push_back(t[0]);
        indices.push_back(t[1]);
        indices.push_back(t[2]);
    }

    glBindVertexArray(vao_);
    glBindBuffer(GL_ARRAY_BUFFER, vbo_);
    glBufferData(GL_ARRAY_BUFFER, static_cast<GLsizeiptr>(positions.size() * sizeof(float)),
                 positions.empty() ? nullptr : positions.data(), GL_DYNAMIC_DRAW);
    glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, ebo_);
    glBufferData(GL_ELEMENT_ARRAY_BUFFER,
                 static_cast<GLsizeiptr>(indices.size() * sizeof(std::uint32_t)),
                 indices.empty() ? nullptr : indices.data(), GL_DYNAMIC_DRAW);
    glBindVertexArray(0);
    index_count_ = indices.size();
}

void MeshRenderer::clear() {
    index_count_ = 0;
}

void MeshRenderer::draw(const Mat4& mvp, float r, float g, float b, float a) const {
    if (index_count_ == 0) return;
    glUseProgram(program_);
    glUniformMatrix4fv(static_cast<GLint>(mvp_uniform_loc_), 1, GL_FALSE, mvp.data());
    glUniform4f(static_cast<GLint>(color_uniform_loc_), r, g, b, a);

    // Blend so the far side of the envelope shows through the near side -
    // a solid wireframe hides the points it is supposed to be enclosing.
    // Depth writes stay off for the same reason, while the depth TEST stays
    // on so the surface is still occluded correctly by anything in front.
    glEnable(GL_BLEND);
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
    glDepthMask(GL_FALSE);
    glPolygonMode(GL_FRONT_AND_BACK, GL_LINE);

    glBindVertexArray(vao_);
    glDrawElements(GL_TRIANGLES, static_cast<GLsizei>(index_count_), GL_UNSIGNED_INT, nullptr);
    glBindVertexArray(0);

    // Restore the state the rest of the frame expects. ImGui in particular
    // renders filled triangles and would come out as outlines otherwise.
    glPolygonMode(GL_FRONT_AND_BACK, GL_FILL);
    glDepthMask(GL_TRUE);
    glDisable(GL_BLEND);
}

} // namespace gm::view
