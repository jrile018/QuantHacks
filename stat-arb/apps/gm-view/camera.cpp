#include "camera.hpp"

#include <algorithm>
#include <cmath>

namespace gm::view {

namespace {

struct Vec3 {
    float x, y, z;
};

Vec3 sub(Vec3 a, Vec3 b) { return {a.x - b.x, a.y - b.y, a.z - b.z}; }
Vec3 cross(Vec3 a, Vec3 b) {
    return {a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x};
}
float dot(Vec3 a, Vec3 b) { return a.x * b.x + a.y * b.y + a.z * b.z; }
Vec3 normalize(Vec3 v) {
    float len = std::sqrt(dot(v, v));
    if (len < 1e-8f) return {0.0f, 0.0f, 0.0f};
    return {v.x / len, v.y / len, v.z / len};
}

} // namespace

Mat4 mat4_identity() {
    Mat4 m{};
    m[0] = m[5] = m[10] = m[15] = 1.0f;
    return m;
}

Mat4 mat4_multiply(const Mat4& a, const Mat4& b) {
    Mat4 result{};
    for (int col = 0; col < 4; ++col) {
        for (int row = 0; row < 4; ++row) {
            float sum = 0.0f;
            for (int k = 0; k < 4; ++k) sum += a[static_cast<std::size_t>(k * 4 + row)] *
                                                b[static_cast<std::size_t>(col * 4 + k)];
            result[static_cast<std::size_t>(col * 4 + row)] = sum;
        }
    }
    return result;
}

Mat4 mat4_perspective(float fovy_radians, float aspect, float z_near, float z_far) {
    Mat4 m{};
    float f = 1.0f / std::tan(fovy_radians / 2.0f);
    m[0] = f / aspect;
    m[5] = f;
    m[10] = (z_far + z_near) / (z_near - z_far);
    m[11] = -1.0f;
    m[14] = (2.0f * z_far * z_near) / (z_near - z_far);
    return m;
}

Mat4 mat4_look_at(float eye_x, float eye_y, float eye_z, float target_x, float target_y, float target_z,
                   float up_x, float up_y, float up_z) {
    Vec3 eye{eye_x, eye_y, eye_z};
    Vec3 target{target_x, target_y, target_z};
    Vec3 up{up_x, up_y, up_z};

    Vec3 forward = normalize(sub(target, eye));
    Vec3 right = normalize(cross(forward, up));
    Vec3 new_up = cross(right, forward);

    Mat4 m{};
    m[0] = right.x;
    m[4] = right.y;
    m[8] = right.z;
    m[1] = new_up.x;
    m[5] = new_up.y;
    m[9] = new_up.z;
    m[2] = -forward.x;
    m[6] = -forward.y;
    m[10] = -forward.z;
    m[15] = 1.0f;
    m[12] = -dot(right, eye);
    m[13] = -dot(new_up, eye);
    m[14] = dot(forward, eye);
    return m;
}

void OrbitCamera::orbit(float delta_yaw, float delta_pitch) {
    yaw += delta_yaw;
    pitch = std::clamp(pitch + delta_pitch, -1.5f, 1.5f);
}

void OrbitCamera::zoom(float delta_distance) { distance = std::max(0.1f, distance + delta_distance); }

Mat4 OrbitCamera::view_matrix() const {
    float eye_x = target_x + distance * std::cos(pitch) * std::sin(yaw);
    float eye_y = target_y + distance * std::sin(pitch);
    float eye_z = target_z + distance * std::cos(pitch) * std::cos(yaw);
    return mat4_look_at(eye_x, eye_y, eye_z, target_x, target_y, target_z, 0.0f, 1.0f, 0.0f);
}

} // namespace gm::view
