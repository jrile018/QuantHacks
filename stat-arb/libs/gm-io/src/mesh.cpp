#include <gm-io/mesh.hpp>

#include <bit>
#include <cstring>
#include <fstream>
#include <string>

namespace gm::io {
namespace {

// The format is defined as little-endian. Every platform this project
// targets (MSVC and GCC on x86-64, ADR-004) is little-endian, so rather than
// carrying byte-swapping code that no CI job would ever exercise, a port to a
// big-endian target fails to compile here instead of silently writing files
// that claim to be gmmesh and are not.
static_assert(std::endian::native == std::endian::little,
              "the .gmmesh format is little-endian; a big-endian port must add byte swapping "
              "here rather than write mislabelled files");

constexpr char kMagic[6] = {'G', 'M', 'M', 'E', 'S', 'H'};
constexpr std::size_t kHeaderBytes = 24;
constexpr std::size_t kVertexBytes = 3 * sizeof(double);   // 24
constexpr std::size_t kTriangleBytes = 3 * sizeof(std::uint32_t); // 12

template <typename T>
void append_raw(std::string& out, const T& value) {
    static_assert(std::is_trivially_copyable_v<T>);
    const auto* bytes = reinterpret_cast<const char*>(&value);
    out.append(bytes, sizeof(T));
}

template <typename T>
T read_raw(const char* data) {
    static_assert(std::is_trivially_copyable_v<T>);
    T value{};
    std::memcpy(&value, data, sizeof(T));
    return value;
}

} // namespace

gm::VoidResult write_gmmesh(const MeshData& mesh, const std::filesystem::path& path) {
    // An out-of-range index makes a mesh that crashes whatever draws it.
    // Refusing to write is strictly better than leaving that on disk under a
    // run directory ADR-017 declares immutable.
    for (std::size_t t = 0; t < mesh.triangles.size(); ++t) {
        for (std::uint32_t index : mesh.triangles[t]) {
            if (index >= mesh.vertices.size()) {
                return tl::unexpected(gm::Error::make(
                    gm::ErrorCode::kValidationFailure,
                    "mesh triangle references a vertex that does not exist",
                    "triangle " + std::to_string(t) + " index " + std::to_string(index) +
                        " with " + std::to_string(mesh.vertices.size()) + " vertices"));
            }
        }
    }

    std::string buffer;
    buffer.reserve(kHeaderBytes + mesh.vertices.size() * kVertexBytes +
                   mesh.triangles.size() * kTriangleBytes);
    buffer.append(kMagic, sizeof(kMagic));
    append_raw(buffer, kGmMeshVersion);
    append_raw(buffer, static_cast<std::uint64_t>(mesh.vertices.size()));
    append_raw(buffer, static_cast<std::uint64_t>(mesh.triangles.size()));
    for (const auto& v : mesh.vertices) {
        append_raw(buffer, v[0]);
        append_raw(buffer, v[1]);
        append_raw(buffer, v[2]);
    }
    for (const auto& t : mesh.triangles) {
        append_raw(buffer, t[0]);
        append_raw(buffer, t[1]);
        append_raw(buffer, t[2]);
    }

    std::error_code ec;
    if (path.has_parent_path()) {
        std::filesystem::create_directories(path.parent_path(), ec);
        if (ec) {
            return tl::unexpected(gm::Error::make(gm::ErrorCode::kIoFailure,
                                                   "could not create mesh output directory",
                                                   path.parent_path().string() + ": " +
                                                       ec.message()));
        }
    }
    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    if (!out) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kIoFailure,
                                               "could not open mesh file for writing",
                                               path.string()));
    }
    out.write(buffer.data(), static_cast<std::streamsize>(buffer.size()));
    out.close();
    if (!out) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kIoFailure,
                                               "failed while writing mesh file", path.string()));
    }
    return {};
}

Result<MeshData> read_gmmesh(const std::filesystem::path& path) {
    std::error_code ec;
    if (!std::filesystem::exists(path, ec)) {
        return tl::unexpected(
            gm::Error::make(gm::ErrorCode::kNotFound, "mesh file does not exist", path.string()));
    }

    std::ifstream in(path, std::ios::binary);
    if (!in) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kIoFailure,
                                               "could not open mesh file", path.string()));
    }
    const std::string bytes{std::istreambuf_iterator<char>(in),
                            std::istreambuf_iterator<char>()};

    if (bytes.size() < kHeaderBytes) {
        return tl::unexpected(gm::Error::make(
            gm::ErrorCode::kParseFailure, "mesh file is shorter than its header",
            path.string() + ": " + std::to_string(bytes.size()) + " bytes"));
    }
    if (std::memcmp(bytes.data(), kMagic, sizeof(kMagic)) != 0) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kParseFailure,
                                               "file is not a .gmmesh (bad magic)",
                                               path.string()));
    }
    const auto version = read_raw<std::uint16_t>(bytes.data() + 6);
    if (version != kGmMeshVersion) {
        // ADR-017: every consumer validates the version and refuses what it
        // does not understand, rather than reading it hopefully.
        return tl::unexpected(gm::Error::make(
            gm::ErrorCode::kSchemaVersionMismatch, "unsupported .gmmesh version",
            path.string() + ": file is version " + std::to_string(version) + ", this build reads " +
                std::to_string(kGmMeshVersion)));
    }

    const auto n_vertices = read_raw<std::uint64_t>(bytes.data() + 8);
    const auto n_triangles = read_raw<std::uint64_t>(bytes.data() + 16);

    // Check the length the header implies against the length on disk BEFORE
    // reserving anything. A corrupt header claiming 2^63 vertices must not be
    // able to ask for that much memory first and fail second.
    const std::uint64_t expected =
        static_cast<std::uint64_t>(kHeaderBytes) + n_vertices * kVertexBytes +
        n_triangles * kTriangleBytes;
    const bool overflowed = n_vertices > (UINT64_MAX / kVertexBytes) ||
                            n_triangles > (UINT64_MAX / kTriangleBytes);
    if (overflowed || expected != bytes.size()) {
        return tl::unexpected(gm::Error::make(
            gm::ErrorCode::kParseFailure, "mesh file length does not match its header",
            path.string() + ": header implies " + (overflowed ? std::string{"an impossible size"}
                                                              : std::to_string(expected)) +
                " bytes, file is " + std::to_string(bytes.size())));
    }

    MeshData mesh;
    mesh.vertices.resize(static_cast<std::size_t>(n_vertices));
    mesh.triangles.resize(static_cast<std::size_t>(n_triangles));
    const char* cursor = bytes.data() + kHeaderBytes;
    for (auto& v : mesh.vertices) {
        v[0] = read_raw<double>(cursor);
        v[1] = read_raw<double>(cursor + 8);
        v[2] = read_raw<double>(cursor + 16);
        cursor += kVertexBytes;
    }
    for (auto& t : mesh.triangles) {
        t[0] = read_raw<std::uint32_t>(cursor);
        t[1] = read_raw<std::uint32_t>(cursor + 4);
        t[2] = read_raw<std::uint32_t>(cursor + 8);
        cursor += kTriangleBytes;
    }

    // A file can be exactly the right length and still describe a mesh that
    // would index past the end of the vertex buffer.
    for (std::size_t i = 0; i < mesh.triangles.size(); ++i) {
        for (std::uint32_t index : mesh.triangles[i]) {
            if (index >= mesh.vertices.size()) {
                return tl::unexpected(gm::Error::make(
                    gm::ErrorCode::kValidationFailure,
                    "mesh triangle references a vertex that does not exist",
                    path.string() + ": triangle " + std::to_string(i) + " index " +
                        std::to_string(index) + " with " +
                        std::to_string(mesh.vertices.size()) + " vertices"));
            }
        }
    }
    return mesh;
}

} // namespace gm::io
