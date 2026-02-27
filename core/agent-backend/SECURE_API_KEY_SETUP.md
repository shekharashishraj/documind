# Secure API Key Setup Guide

This project reads `OPENAI_API_KEY` from:

1. Environment variable (`OPENAI_API_KEY`)
2. OS keyring (`service="openai"`, `username="api_key"`)

Use one of these methods.

---

## Option 1 (Recommended): Keyring

```bash
pip install keyring
keyring set openai api_key sk-proj-YOUR_KEY
python -m src.api_server
```

Why this is best:
- Key is stored in encrypted OS credential storage
- No plaintext key in repo files

---

## Option 2: Environment Variable

```bash
export OPENAI_API_KEY=sk-proj-YOUR_KEY
python -m src.api_server
```

Persistent on macOS (zsh):

```bash
echo 'export OPENAI_API_KEY=sk-proj-YOUR_KEY' >> ~/.zshrc
source ~/.zshrc
```

---

## Option 3: `.env` for local dev only

```bash
cp .env.example .env
nano .env
# OPENAI_API_KEY=sk-proj-YOUR_KEY
python -m src.api_server
```

If you use `.env`, keep it local and never commit it.

---

## Verify setup

```bash
curl http://localhost:8000/health
```

Expected response includes:
- `status: "ok"`
- Supported domains list

You can also test upload flow:

```bash
curl -X POST http://localhost:8000/analyze-pdf \
	-F "file=@/absolute/path/to/file.pdf" \
	-F "query=Summarize key insights"
```

---

## If key is exposed

1. Revoke it in OpenAI dashboard immediately
2. Generate a new key
3. Update keyring/env/.env value
4. Review usage logs
