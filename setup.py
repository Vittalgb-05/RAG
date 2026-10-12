"""Setup and packaging configuration for Local-First Multimodal PDF Intelligence System."""

from pathlib import Path
from setuptools import find_packages, setup

# Read the long description from README.md
readme_path = Path(__file__).parent / "README.md"
long_description = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""

# Read core dependencies from requirements.txt
req_path = Path(__file__).parent / "requirements.txt"
requirements = []
if req_path.exists():
    for line in req_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            requirements.append(line)

setup(
    name="rag-assistant",
    version="1.0.0",
    description="Local-First Multimodal PDF Intelligence System with Hybrid Retrieval and VLM",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="RAG Team",
    python_requires=">=3.11",
    packages=find_packages(),
    py_modules=[
        "citation_validator",
        "doc_store",
        "docling_reader",
        "groq_provider",
        "hybrid_retriever",
        "litellm_provider",
        "llama_cpp_provider",
        "local_embedding",
        "local_llm",
        "main",
        "model_provider",
        "models",
        "ocr_fallback",
        "pdf_reader",
        "prompt_budget",
        "resource_telemetry",
        "start",
        "summarizer",
        "upload_validation",
        "vector_index",
        "visual_analyzer",
    ],
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "rag-assistant=start:main",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
)
