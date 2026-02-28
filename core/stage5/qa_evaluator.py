"""QA accuracy evaluation for Stage 5 using eval_pdf_qa.json."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from openai import OpenAI


_NOT_ANSWERABLE_PHRASES = frozenset({
    "not answerable",
    "not-answerable",
    "cannot be determined",
    "cannot determine",
    "not mentioned",
    "not stated",
    "not provided",
    "unknown",
    "n/a",
})


def _normalize(text: str) -> str:
    """Lowercase, strip whitespace and punctuation for comparison."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _is_match(predicted: str, gold_answers: list[str], answer_type: str) -> bool:
    """Check if predicted answer matches any gold answer."""
    pred_norm = _normalize(predicted)

    if answer_type == "not-answerable":
        return any(phrase in pred_norm for phrase in _NOT_ANSWERABLE_PHRASES)

    for gold in gold_answers:
        if _normalize(gold) == pred_norm:
            return True
        # Substring match for extractive/abstractive answers
        if _normalize(gold) in pred_norm or pred_norm in _normalize(gold):
            return True

    return False


def _load_qa_for_doc(doc_id: str, qa_dataset_path: str) -> list[dict[str, Any]]:
    """Load QA pairs for a specific doc_id from the dataset."""
    path = Path(qa_dataset_path)
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return []
    doc_entry = data.get(doc_id)
    if not doc_entry:
        return []
    return doc_entry.get("questions", [])


def evaluate_qa_accuracy(
    doc_id: str,
    text: str,
    qa_dataset_path: str,
    model: str = "gpt-4o",
    api_key: str | None = None,
) -> float | None:
    """
    Return fraction of QA questions correctly answered (0.0–1.0).

    Uses the eval_pdf_qa.json dataset to find questions for the given doc_id,
    then prompts the LLM to answer each question based on the provided text.
    Returns None if no questions are found for the doc_id.
    """
    questions = _load_qa_for_doc(doc_id, qa_dataset_path)
    if not questions:
        return None

    client = OpenAI(api_key=api_key)
    n_correct = 0
    n_total = len(questions)

    # Truncate text to avoid token overflow
    truncated_text = text[:60000]

    for qa in questions:
        question = qa.get("question", "")
        gold_answers = qa.get("answers", [])
        answer_type = qa.get("answer_type", "extractive")

        if not question or not gold_answers:
            n_total -= 1
            continue

        prompt = (
            "You are a document QA system. Given the document text below, answer the question "
            "as concisely as possible. If the answer cannot be found in the document, respond "
            "with 'not answerable'. Do not add explanation.\n\n"
            f"Document:\n{truncated_text}\n\n"
            f"Question: {question}\n\n"
            "Answer:"
        )

        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=128,
            )
            predicted = response.choices[0].message.content or ""
        except Exception:
            # Count as incorrect on API error
            continue

        if _is_match(predicted, gold_answers, answer_type):
            n_correct += 1

    if n_total <= 0:
        return None

    return n_correct / n_total
