# ------------------------------------------------------------------
# Unit Tests for AiModel (local_llm.py)
# Tests API key validation, prompt assembly, and streaming generator
# ------------------------------------------------------------------

import pytest
from unittest.mock import MagicMock
from local_llm import AiModel


def test_ai_model_missing_key_raises(monkeypatch):
    """
    Verify AiModel raises ValueError when GROQ_API_KEY is missing.
    Documents and asserts Risk 1 handling from CONCERNS.md.
    """
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(ValueError, match="GROQ_API_KEY is not set"):
        AiModel()


def test_ai_model_prompt_assembly(fake_env_groq_key, mock_groq_client):
    """Verify prompt formatting and context inclusion."""
    model = AiModel()
    assert model.model_name == "openai/gpt-oss-20b"

    mock_embedding = MagicMock()
    mock_embedding.get_context.return_value = "Retrieved document text context line."

    chat_history = [
        {"role": "user", "content": "What is the project name?"},
        {"role": "assistant", "content": "Local Multimodal PDF Intelligence."},
    ]

    tokens = list(
        model.ask_a_question_from_pdf_stream(
            pdf_path="",
            prompt="What is the latency target?",
            local_embedding=mock_embedding,
            chat_history=chat_history,
        )
    )

    # Verify get_context called with contextualized query
    mock_embedding.get_context.assert_called_once()

    # Verify groq client called with correct parameters
    call_args = mock_groq_client.chat.completions.create.call_args[1]
    assert call_args["model"] == "openai/gpt-oss-20b"
    assert call_args["stream"] is True

    messages = call_args["messages"]
    system_msg = messages[0]["content"]
    assert "Document Text:" in system_msg
    assert "Retrieved document text context line." in system_msg

    # Verify conversation history passed
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "What is the project name?"

    # Verify current user question is last message
    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"] == "What is the latency target?"


def test_ai_model_streaming_yield(fake_env_groq_key, mock_groq_client):
    """Verify the generator yields stream tokens one by one."""
    model = AiModel()

    mock_embedding = MagicMock()
    mock_embedding.get_context.return_value = "Sample context."

    generator = model.ask_a_question_from_pdf_stream(
        pdf_path="",
        prompt="Tell me about the architecture",
        local_embedding=mock_embedding,
    )

    tokens = list(generator)
    assert tokens == ["This ", "is ", "a ", "grounded ", "answer."]
    assert "".join(tokens) == "This is a grounded answer."
