#pragma once

// Minimal orbit camera and 4x4 matrix math for gm-view (ADR-018).
// Deliberately hand-rolled rather than pulling in a matrix library
// (GLM etc.) - gm-view needs exactly two matrices (perspective,
// look-at) and one small orbit-control state machine, not a general
// linear algebra dependency (Eigen already serves that role elsewhere
// in the codebase; introducing it here too, just for 4x4 float
// matrices in OpenGL's column-major convention, would be more surface
// area than the problem needs).

#include <array>
#include <cstdint>

namespace gm::view {

/// Column-major 4x4, matching OpenGL's convention directly (so the raw
/// float array can be handed to glUniformMatrix4fv with transpose=GL_FALSE).
using Mat4 = std::array<float, 16>;

[[nodiscard]] Mat4 mat4_identity();
[[nodiscard]] Mat4 mat4_multiply(const Mat4& a, const Mat4& b);  // a * b
[[nodiscard]] Mat4 mat4_perspective(float fovy_radians, float aspect, float z_near, float z_far);
[[nodiscard]] Mat4 mat4_look_at(float eye_x, float eye_y, float eye_z, float target_x, float target_y,
                                 float target_z, float up_x, float up_y, float up_z);

/// Spherical-coordinate orbit camera around a fixed target point.
/// yaw/pitch in radians; distance > 0. Pitch is clamped away from the
/// poles to avoid the camera flipping through the up vector.
struct OrbitCamera {
    float target_x = 0.0f, target_y = 0.0f, target_z = 0.0f;
    float distance = 5.0f;
    float yaw = 0.0f;
    float pitch = 0.3f;

    void orbit(float delta_yaw, float delta_pitch);
    void zoom(float delta_distance);
    [[nodiscard]] Mat4 view_matrix() const;
};

} // namespace gm::view
