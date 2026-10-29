---
status: resolved
trigger: |
  omprakash@omprakash-Victus-by-HP-Gaming-Laptop-15-fb0xxx:~/Documents/RAG$ python3 start.py --start-llama
  ...
  🚀 Launching Streamlit web application on http://localhost:8501 ...
     Press Ctrl+C to stop the server.

  /usr/bin/python3: No module named streamlit

  🛑 Stopping background llama-server...  why is streamlit not being setup with its modules in setup.py?
created: 2026-10-29
updated: 2026-10-29
---

# Debug Session: streamlit missing because dependencies are never installed

**Session Slug:** `streamlit-missing-setup-deps`

## Symptoms

**Expected behavior:**
`python3 setup.py --llama-server` (or a full `python3 setup.py`) leaves the interpreter used by
`start.py` with the project's Python dependencies installed, so `python3 start.py --start-llama`
launches Streamlit successfully.

**Actual behavior:**
llama-server starts fine, then Streamlit launch fails:
`/usr/bin/python3: No module named streamlit`. start.py correctly shuts the background server down.

**Error messages:**
`/usr/bin/python3: No module named streamlit` (no traceback; it is a child-process import error).

**Timeline:**
First run on this Linux machine. Earlier `python3 setup.py --llama-server` reported success
(only llama-server was configured). No virtualenv exists in the repo.

**Reproduction:**
Fresh Linux (Ubuntu 24.04) checkout, no venv activated:
`python3 setup.py --llama-server` then `python3 start.py --start-llama`.

## Initial Evidence (orchestrator, pre-delegation)

1. `requirements.txt:3` **does** contain `streamlit==1.66.1`; `requirements-lock.txt` also pins it.
   So the dependency is declared — it is never installed, not missing from the manifest.

2. `--llama-server` is a narrow flag. The CLI dispatch routes it straight to
   `setup_llama_server()` and skips `install_dependencies()` entirely, so a user who follows the
   printed "run: python start.py --start-llama" hint gets an interpreter with zero deps.

3. Even full `python3 setup.py` cannot install deps on this host:
   `install_dependencies()` (setup.py:764) runs `[sys.executable, "-m", "pip", "install", "-r", ...]`,
   and Ubuntu 24.04 ships `/usr/lib/python3.12/EXTERNALLY-MANAGED` (PEP 668). Verified:
   ```
   python3 -m pip install --dry-run "streamlit==1.66.1"
   error: externally-managed-environment
   ```
4. That failure is swallowed: `run_full_setup()` prints
   `⚠️ Warning: Dependency installation reported issues. Continuing with setup...`
   and still ends with `🎉 Setup Complete!` + the launch hint. The non-zero pip result never
   reaches the exit code.
5. No venv handling exists anywhere: `grep -n "venv" setup.py start.py` returns nothing.
   README.md:131 does document `python -m venv .venv` as a manual prerequisite, so the code
   assumes, but never enforces, a venv.
6. `start.py` launches Streamlit via `subprocess`/`sys.executable` (start.py:267) with no
   pre-flight dependency check, so it starts llama-server first and only fails afterwards.

## User decision (2026-10-29)

Fix approach: **auto-create `.venv` + fail fast.**
- Full `setup.py` must detect PEP 668 / non-writable system Python, create `.venv`, install
  dependencies and the package into it, and print the exact launch command using that interpreter.
- `start.py` must fail fast with actionable guidance when the current interpreter is missing
  required deps — before launching llama-server.
- `--llama-server` should not silently leave the user in an unusable environment.

## Verification of the hypothesis (executor)

Confirmed all six evidence items against the working tree before changing anything:

- `/usr/lib/python3.12/EXTERNALLY-MANAGED` exists on this host (PEP 668).
- `python3 -c "import streamlit"` → `ModuleNotFoundError`; `/usr/bin/python3` has no pytest either.
- `setup.py` had no `sysconfig`/venv logic and `run_full_setup()` returned `0` unconditionally
  after printing "Setup Complete".
- `start.py main()` spawned llama-server before ever importing streamlit.

## Resolution

**root_cause:** Dependency installation was never guaranteed to succeed: `--llama-server`
dispatched around `install_dependencies()` by design, and the full-setup path's `pip install`
targeted `sys.executable`, which PEP 668 rejects on this host — a failure `run_full_setup()`
downgraded to a warning while still reporting success and printing a launch hint. With no venv
created or enforced and no pre-flight import check in `start.py`, the missing module surfaced
only after llama-server had been started.

**fix:** `setup.py` now provisions a runnable interpreter and fails closed:

- Detect an uninstallable interpreter (`sys.prefix != sys.base_prefix` check, PEP 668
  `EXTERNALLY-MANAGED` marker, non-writable `purelib`) and redirect the install into an isolated
  environment — `.venv` by default, overridable via `--venv-path` or `RAG_VENV_PATH`.
- Provisioning installs `requirements.txt`/`requirements-lock.txt` plus `pip install -e .` into
  that environment and verifies `REQUIRED_RUNTIME_MODULES` (streamlit first) import through it; a
  usable environment is reused without re-installing.
- `install_dependencies()` also verifies imports after a successful system pip run, so a zero
  exit code alone never counts as success.
- `run_full_setup()` returns `1` with a `❌ Setup failed` block (and skips the multi-GB model and
  llama-server work) when provisioning fails; on success it prints the exact launch command for
  the interpreter that was provisioned, e.g. `.venv/bin/python start.py --start-llama`.
- `--llama-server` stays llama-only but runs `report_dependency_preflight()` afterwards, naming the
  missing modules, the interpreter, `python3 setup.py`, and the correct launch command.
- `start.py` gained `missing_required_modules()` / `check_dependencies()`, called from `main()`
  before any subprocess exists; a miss prints the missing modules, `sys.executable`, the
  remediation and the venv launch command, then exits `3` — llama-server is never started.

**verification:** `tests/test_setup_dependencies.py` (new) and `tests/test_start_launcher.py`
(extended) cover PEP 668 detection, venv path resolution, reuse vs create, pip failure, import
verification on both branches, `run_full_setup()` exit codes, the llama-only pre-flight, and the
launcher fail-fast order. 75 targeted tests pass; `ruff check`/`ruff format --check` clean.
Real runs: a throwaway venv provisioned from scratch installed streamlit and verified the import
(reuse path re-ran in 0.7s), an uninstallable requirement returned `False` from
`install_dependencies()`, `python3 start.py --start-llama` exited 3 with no llama-server process
left behind, and `python3 setup.py --llama-server` reported the missing dependencies with the
correct launch command.

## Prevention (blameless postmortem)

- **why not caught:** no gate checked that the installer's definition of success ("pip exited 0")
  matched the app's definition ("the launcher interpreter can import streamlit"); `--llama-server`
  had no post-condition at all, and the launcher had no pre-flight, so the two halves were only
  ever tested separately.
- **guard:** the import probe in `missing_modules()` is now the single success criterion on every
  dependency path (system pip, venv provisioning, llama-only pre-flight), and
  `check_dependencies()` makes the launcher assert it before spawning anything; unit tests pin
  both, including the case where pip reports success but the module still cannot import.
