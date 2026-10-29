---
status: resolved
trigger: |
  omprakash@omprakash-Victus-by-HP-Gaming-Laptop-15-fb0xxx:~/Documents/RAG$ python3 setup.py --llama-server
  ✓ Project directories initialized (models/, data/, .cache/, tools/)
  ====================================================================
    ⚙️ LLAMA-SERVER ACQUISITION & NATIVE RUNTIME SETUP
  ====================================================================
    • Platform: linux | NVIDIA GPU Detected: False (cpu_only=False)
    • Targeting Linux x86_64 CPU build...
    ⬇️ Downloading llama-b11960-linux.tar.gz (Mirror 1/2)...
       URL: https://github.com/ggml-org/llama.cpp/releases/download/b11960/llama-b11960-bin-ubuntu-x64.tar.gz
       [========================] 100.0% | 21.6 MB / 21.6 MB | 2.7 MB/ss
    ✓ Successfully verified and saved llama-b11960-linux.tar.gz (21.6 MB)
    📦 Extracting llama-b11960-linux.tar.gz to llama-server...
    ❌ Could not successfully configure llama-server.
       Please refer to docs/LOCAL_INFERENCE.md for manual setup steps.
  ====================================================================
created: 2026-10-29
updated: 2026-10-29
---
# Debug Session: llama-server setup extraction fails on Linux

**Session Slug:** `llama-server-setup-fails`

## Symptoms

**Expected behavior:**
`python3 setup.py --llama-server` downloads the pinned llama.cpp release, installs it to
`tools/llama-server/`, verifies `llama-server --version`, and reports success so that
`start.py` / the provider can launch a local server.

**Actual behavior:**
Download and extraction report success, then setup prints
`❌ Could not successfully configure llama-server.` and exits non-zero. No stack trace.

**Error messages:**
Only the generic final failure line. Extraction itself raises nothing (the
`❌ Error extracting ...` branch is not reached).

**Timeline:**
First attempt on this Linux machine. Never worked here. Release pinned to
`EXPECTED_LLAMA_CPP_BUILD` = b11960 (commit d617919 "chore(deps,setup): upgrade pinned
dependencies and runtime build detection" moved to this build).

**Reproduction:**
`python3 setup.py --llama-server` in the repo root on Linux x86_64 without an NVIDIA GPU.

## Initial Evidence (orchestrator, pre-delegation)

1. Extraction produced a **nested** directory instead of flattening into the destination:
   the tarball's members are all under a top-level `llama-b11960/` directory, so the tree is
   `tools/llama-server/llama-b11960/llama-server` while `get_local_llama_server_path()`
   expects `tools/llama-server/llama-server`. Step 3's `if exe_path.exists()` therefore
   never matches and the generic failure line prints.
   - `ls tools/llama-server` → only `llama-b11960/`
   - `find tools/llama-server -maxdepth 3 -name "llama-server*"` →
     `tools/llama-server/llama-b11960/llama-server`

2. Even at the correct path the binary cannot load: the release ships shared-library
   **symlinks** (`libllama-common.so.0 -> libllama-common.so.0.8.0`, plus 9 more soname
   links), and `safe_extract_archive()` skips every symlink/hardlink member:
   ```python
   if member.issym() or member.islnk():
       # Links could point outside the extraction root; skip them.
       continue
   ```
   - `cd tools/llama-server/llama-b11960 && ./llama-server --version` →
     `./llama-server: error while loading shared libraries: libllama-common.so.0: cannot open shared object file: No such file or directory`
   - Only versioned files (`libllama-common.so.0.8.0`) were extracted; all 10 soname links
     are missing.

3. `safe_extract_archive()` has no flattening option, and
   `download_and_extract_archive()` ignores the return value of the Linux call at
   setup.py:601 (its `bool` result is discarded), so extraction/verification failures
   are invisible apart from the final generic message.

## Current Focus

**hypothesis:** Two compounding defects in the Linux install path: (a) `safe_extract_archive()` preserves the archive's top-level `llama-b11960/` directory so the binary lands one level deeper than `get_local_llama_server_path()` expects; (b) the same function drops symlink members, removing every `.so` soname link the binary needs at load time — so even a flattened layout fails verification.

**test:** Extract the pinned tarball with the current code path and assert `tools/llama-server/llama-server` exists and `llama-server --version` exits 0; inspect which tar members are symlinks.

**expecting:** With the archive's real layout, the current code fails both assertions; a flattening + symlink-safe (contained) extraction passes them.

**next_action:** gather initial evidence

## Resolution

- root_cause: |
    1. **Nested layout:** the Linux release tarball stores every member under a single top-level
       `llama-b11960/` directory, and `safe_extract_archive()` preserved it. The binary landed at
       `tools/llama-server/llama-b11960/llama-server` while `get_local_llama_server_path()` checks
       `tools/llama-server/llama-server`, so final verification never ran and the generic
       `❌ Could not successfully configure llama-server.` line printed.
    2. **Dropped soname links:** the same function skipped every symlink/hardlink member for
       path-traversal safety, removing the 10 soname links the binary needs at load time
       (`libllama-common.so.0 -> libllama-common.so.0.8.0`, `libllama.so -> libllama.so.0`, …).
       Even a flattened binary therefore failed with
       `error while loading shared libraries: libllama-common.so.0`.
    3. **Swallowed failure:** the Linux branch of `setup_llama_server()` discarded
       `download_and_extract_archive()`'s boolean result, so neither a download failure nor a
       missing executable after extraction was reported distinctly.
- fix: |
    - `safe_extract_archive(archive_path, dest_dir, *, strip_root=False)` now:
      - validates member paths lexically (`os.path.normpath`) instead of `Path.resolve()`, which
        previously followed pre-existing symlinks from an earlier extraction and could rewrite
        the link targets (corrupting a re-install); it also rejects parents that are symlinks;
      - extracts regular files/directories explicitly and recreates symlinks/hardlinks only when
        their target resolves inside `dest_dir`, deferring chained links (`libfoo.so ->
        libfoo.so.1 -> libfoo.so.1.0`) until their target exists, and skipping escapes with a
        `⚠️` warning;
      - optionally strips a single enclosing directory shared by every member (`strip_root`).
      The zip branch is unchanged, so the flat Windows archives still extract as before.
    - `download_and_extract_archive(..., strip_root=False)` forwards the flag.
    - The Linux branch of `setup_llama_server()` passes `strip_root=True`, keeps the boolean
      result, and prints explicit `❌ Failed to download or extract …` /
      `❌ llama-server was not found after extracting …` diagnostics before final verification.
    - New regression tests cover root stripping + soname link restoration (incl. hardlinks),
      re-extraction over existing links, zip no-flatten behaviour, and rejection of escaping
      links/traversal members.
- verification: |
    - Real end-to-end clean install: `rm -rf tools/llama-server && python3 setup.py --llama-server`
      → `✓ llama-server successfully configured at: .../tools/llama-server/llama-server`, exit 0;
      `tools/llama-server/llama-server --version` →
      `version: 0.8.0-dev (build 11960, commit 8642541b2)`, exit 0. Layout is flat (no nested dir)
      with all 10 soname symlinks present.
    - Re-install over an existing tree: `python3 setup.py --llama-server --force` → exit 0, version
      still runs, 10 links, 0 nested directories (exercises the symlink-replacement path).
    - `pytest tests/test_setup_llama.py tests/test_setup_checksums.py tests/test_runtime_info.py
      tests/test_packaging.py tests/test_start_launcher.py -q` → 59 passed.
    - `ruff check setup.py tests/test_setup_llama.py` → All checks passed;
      `ruff format --check` → both files already formatted.
- files_changed: |
    setup.py, tests/test_setup_llama.py

