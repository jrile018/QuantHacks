# REIT clock evidence packet paths

`scripts/build_reit_publication_clock_packet.py` reads retained source evidence offline. It creates a new immutable producer packet; Post Benchmark owns canonical acceptance. Exact first-public availability remains unknown where unsupported. The frozen acceptance-plus-24-hours policy remains an assumed replay proxy.

The default path resolver uses the script checkout and existing native path behavior. For a relocated runtime, `--project-root` explicitly selects the runtime project root. Add `--origin-project-root "C:/Users/johnp/OneDrive/Documents/ChatGPT/QuantHaxs"` to map references recorded under that original Windows root into the runtime project root. Relative Windows backslash references are normalized only with this declaration. Runtime absolute paths must remain contained in the runtime project root.

Mapping applies to file access only. Input JSON, Submissions metadata and HTTP receipt bytes remain untouched and their original SHA256 hashes are recorded. Input JSON and JSONL are decoded with `utf-8-sig`, so a retained UTF-8 BOM is accepted while remaining part of the byte hash. The packet records both declared roots in `path_resolution`; no filenames are guessed.

Drive-relative paths, other drives or directories outside the declared origin, `..` traversal, alternate-stream components and symlinks resolving outside the runtime root are rejected. The old origin and new runtime root must be supplied explicitly; there is no automatic search for matching files.

For the root-owned historical qualified run, retain the exact peer manifest, broker receipt ledger, metadata collection and cached Submissions bytes, raw originals and separate source-grade JSONL. Pass `--peer-manifest`, `--broker-receipts`, `--collection-manifest`, `--source-grades`, both root flags and a new `--output-dir`. Root owns the exact remote invocation, input copying, consumer review and resulting manifest. Existing v1/v2 packets are not rewritten.

Focused verification: `.venv/Scripts/python.exe -m unittest tests.test_reit_publication_clocks -q`. The same fixtures can run under Linux Python with timezone data installed; a Windows host without directory-symlink privileges reports a symlink-test skip, which must be verified on the Linux runtime.
