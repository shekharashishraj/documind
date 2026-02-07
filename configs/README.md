# Config

API keys and optional settings are loaded from a **`.env`** file in the project root. Copy `.env.example` to `.env` and fill in your values (do not commit `.env`).

- **MISTRAL_API_KEY**: Set for VLM (Mistral) extraction. Optional if you only run byte_extraction or OCR. Loaded from `.env` or the environment.
- **Tesseract**: Install system Tesseract for OCR (e.g. `brew install tesseract` on macOS, `apt-get install tesseract-ocr` on Linux). `pytesseract` will use the `tesseract` binary from PATH unless you set `TESSERACT_CMD` in the environment or in `.env`.
