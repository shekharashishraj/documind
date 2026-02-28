"""Stage 4a: Plan minimal edits and generate per-strategy PDFs for inspection."""

from core.stage4a.executor import run_stage4a_executor
from core.stage4a.openai_editor import run_stage4a_openai

__all__ = ["run_stage4a_executor", "run_stage4a_openai"]
