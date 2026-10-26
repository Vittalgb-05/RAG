"""Packaging and operator configuration regression tests."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_env_example_documents_recognized_configuration() -> None:
    """The operator template must cover credentials, local inference, and safety toggles."""
    env_example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")

    for key in (
        "GROQ_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "LLAMA_SERVER_URL",
        "LLAMA_SERVER_HOST",
        "LLAMA_SERVER_PORT",
        "DOCLING_ARTIFACTS_PATH",
        "RAG_LOG_LEVEL",
        "RAG_LOG_DIR",
        "RAG_REQUIRE_CHECKSUMS",
        "RAG_ALLOW_NON_LOOPBACK",
    ):
        assert key in env_example, f".env.example is missing {key}"

    assert "gsk_" not in env_example
    assert "sk-" not in env_example


def test_dockerfile_installs_the_locked_dependency_set() -> None:
    """Docker builds must use the same locked dependencies as CI and local setup."""
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "pip install -r requirements-lock.txt" in dockerfile
    assert "pip install -r requirements.txt" not in dockerfile


def test_pytest_warning_filters_are_targeted() -> None:
    """Warnings must be filtered by known message, not globally suppressed."""
    import tomllib

    config = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    filters = config["tool"]["pytest"]["ini_options"]["filterwarnings"]

    assert "ignore::UserWarning" not in filters
    assert "ignore::DeprecationWarning" not in filters
    joined = "\n".join(filters)
    assert "table_names" in joined
    assert "create_fts_index" in joined
    assert "Direct unindexed PDF ingestion" in joined
