<!-- graphicle:start (added by graphicle setup; graphicle disconnect removes it) -->
## Graphicle
Use the `graphicle` MCP server for where or how something works, for questions across files or history, and before changing unfamiliar code: `recall_project` or `query_graph` with the question, then `get_node` and `get_neighbors` for one symbol; answers cite file and lines. For an exact identifier you already know, grep is enough.
Without the server, run `graphicle context "<question>"` in a terminal.
<!-- graphicle:end -->

## Git Branch Discipline

All AI agents and contributors must adhere to strict git hygiene and branch discipline:

1. **Branch Naming Conventions**:
   - `feat/<short-description>`: New features, endpoints, or UI capabilities.
   - `fix/<issue-or-bug>`: Bug fixes, regressions, or security patches.
   - `chore/<task>`: Dependency updates, CI/CD pipelines, tool configurations.
   - `refactor/<module>`: Structural code improvements without behavioral changes.
   - `docs/<subject>`: Documentation, runbooks, or architectural specs.

2. **Commit Standards (Conventional Commits)**:
   - Structure: `<type>(<scope>): <imperative summary>` (e.g., `feat(api): add 3D query trace endpoint`, `fix(retrieval): resolve vector export escaping`).
   - Atomic commits: Group logically cohesive changes together. Do not mix formatting refactors with behavioral fixes.
   - Keep commit messages concise, descriptive, and linked to issue IDs or specifications where applicable.

3. **Repository Hygiene**:
   - Never commit sensitive secrets, API keys, or `.env` files.
   - Never commit model weights (`models/*.gguf`, `tools/llama-server/`), virtual environments (`.venv`), or runtime databases (`data/`).
   - Never commit build output (`frontend/.next/`, `frontend/out/`, `dist/`, `build/`).
   - Run `git status` before committing to verify no untracked scratch files or logs are staged.

4. **Merge & PR Workflow**:
   - Keep feature branches updated against `main`.
   - Before opening a PR or merging, execute the full local quality gate:
     ```bash
     ruff check .
     ruff format --check .
     pytest tests/ -v
     pnpm --dir frontend typecheck
     ```

## Graphicle Workflow Cycles

To maintain accurate structural knowledge of the codebase, integrate Graphicle into your development cycle:

1. **Pre-Modification Discovery**:
   - Before editing unfamiliar modules or cross-cutting boundaries (such as `core/doc_store.py`, `retrieval/hybrid_retriever.py`, or `api/container.py`), inspect relations:
     ```bash
     graphicle context "How are documents indexed and queried across DocStore and HybridRetriever?"
     ```
2. **Post-Change Synchronization**:
   - After completing code modifications, adding new endpoints, or finishing a development phase, immediately run:
     ```bash
     graphicle sync
     ```
   - Verify that all newly created or updated symbols (nodes) and calls/imports (edges) are synchronized without parse errors.
3. **Continuous Index Freshness**:
   - Always run `graphicle sync` before cutting a release branch or opening a pull request to ensure team members and subsequent agents inherit an up-to-date dependency graph.

