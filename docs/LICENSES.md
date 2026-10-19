# Licensing & Third-Party Dependencies

This document clarifies the licensing structure of the project and its external runtime dependencies.

## Project License
The source code written for this project is licensed under the [MIT License](../LICENSE).

## Third-Party Component Licensing

| Component | Upstream License | Distribution Notes |
| :--- | :--- | :--- |
| **PyMuPDF** (`fitz`) | **AGPL-3.0 / Commercial** | PyMuPDF is dual-licensed by Artifex Software Inc. under GNU AGPL-3.0 and commercial terms. If you distribute this application or make it available over a network without commercial licensing, your derivative distribution may be subject to AGPL-3.0 copyleft obligations. Obtain a commercial license from Artifex if closed-source distribution is required. |
| **Docling** | MIT | Permissive license. |
| **RapidOCR / ONNXRuntime** | Apache 2.0 / MIT | Permissive open-source license. |
| **llama.cpp / llama-server** | MIT | Permissive open-source license. |
| **Qwen Models** (Weights) | Qwen Research / Apache 2.0 | Model weights redistribution must adhere to the model's respective community license. |
| **LanceDB** | Apache 2.0 | Permissive open-source vector database. |
| **Sentence-Transformers** | Apache 2.0 | Permissive open-source embedding framework. |

## Notice for Downstream Distributors
Downstream packagers, Docker container distributors, and commercial deployers must ensure compliance with PyMuPDF's AGPL-3.0 terms or replace the rendering engine with a permissive alternative (such as `pdfium` or `pypdf`) prior to binary redistribution.
