"""Retrieval-grounded Q&A over one saved SIGNALDESK analysis."""
from __future__ import annotations

import json
import re
from typing import Any

import pandas as pd

from app.core.config import OLLAMA_MODEL
from app.services.llm_service import OllamaError, active_provider, generate_json

STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "what", "which", "when",
    "where", "why", "how", "does", "did", "are", "was", "were", "can", "could",
    "would", "should", "about", "show", "tell", "give", "me", "all", "some", "their",
    "them", "they", "our", "you", "your", "into", "have", "has", "had", "there", "than",
    "then", "most", "many", "much", "more", "less", "issue", "issues", "problem", "problems",
}


def _stem(token: str) -> str:
    """Small dependency-free normaliser for common English plural/inflection variants."""
    if len(token) > 5 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 5 and token.endswith("ing"):
        return token[:-3]
    if len(token) > 4 and token.endswith("es"):
        return token[:-2]
    if len(token) > 3 and token.endswith("s"):
        return token[:-1]
    return token


def _tokens(text: str) -> set[str]:
    return {
        _stem(token)
        for token in re.findall(r"[a-z0-9]{3,}", str(text).casefold())
        if token not in STOPWORDS
    }


def retrieve_relevant_records(question: str, classified: pd.DataFrame, findings: list[dict], limit: int = 8) -> list[dict]:
    """Simple transparent lexical retrieval with theme-name matching."""
    query_tokens = _tokens(question)
    ranked: list[tuple[int, int, dict[str, Any]]] = []
    finding_by_theme = {str(item.get("theme", "")).casefold(): item for item in findings}
    selected_themes = [theme for theme in finding_by_theme if theme and theme in question.casefold()]

    for position, row in enumerate(classified.to_dict(orient="records")):
        feedback = str(row.get("original_feedback", ""))
        theme = str(row.get("theme", ""))
        feedback_tokens = _tokens(feedback)
        theme_tokens = _tokens(theme)
        overlap = len(query_tokens & (feedback_tokens | theme_tokens))
        if selected_themes and theme.casefold() in selected_themes:
            overlap += 4
        if not query_tokens and not selected_themes:
            overlap = 0
        if overlap > 0:
            ranked.append((overlap, -position, row))

    if not ranked:
        # When the question is broad, retrieve evidence from the most frequent finding.
        top_theme = str(findings[0].get("theme", "")).casefold() if findings else ""
        for position, row in enumerate(classified.to_dict(orient="records")):
            if str(row.get("theme", "")).casefold() == top_theme:
                ranked.append((1, -position, row))

    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    output = []
    for _score, _position, row in ranked[:limit]:
        output.append({
            "record_id": str(row.get("record_id", "")),
            "theme": str(row.get("theme", "")),
            "sentiment": str(row.get("sentiment", "unknown")),
            "emotion": str(row.get("emotion", "unknown")),
            "urgency": str(row.get("urgency", "unknown")),
            "quote": str(row.get("original_feedback", "")),
            "source_id": None if pd.isna(row.get("source_id")) else str(row.get("source_id")),
            "source_row": int(row.get("source_row", 0) or 0),
            "source_type": str(row.get("source_type", "file_upload")),
            "source_reference": str(row.get("source_reference", "") or ""),
            "source_page": (int(row.get("source_page")) if str(row.get("source_page", "")).strip().isdigit() else None),
        })
    return output


def answer_research_question(
    question: str,
    classified: pd.DataFrame,
    findings: list[dict],
    *,
    model_call=generate_json,
) -> dict:
    """Answer from retrieved rows and return only citations present in that retrieval set."""
    question = question.strip()
    if not question:
        raise ValueError("Enter a question about this analysis.")
    if len(question) > 1000:
        raise ValueError("Questions must be 1,000 characters or fewer.")
    retrieved = retrieve_relevant_records(question, classified, findings)
    if not retrieved:
        return {
            "answer": "I couldn't find feedback records relevant to that question in this dataset. Try naming a theme or describing the issue you want to investigate.",
            "cited_evidence": [],
            "answer_method": "retrieval_no_match",
            "caveat": "No matching source records were retrieved.",
        }

    source_ids = {item["record_id"] for item in retrieved}
    # Keep Q&A context bounded for local 4 GB/6 GB VRAM-class models. The returned
    # citations still contain the complete original quote from the saved CSV.
    model_records = [
        {**item, "quote": item["quote"][:1200], "quote_truncated_for_model": len(item["quote"]) > 1200}
        for item in retrieved
    ]
    context = json.dumps(model_records, ensure_ascii=False)
    retrieved_themes = {item["theme"] for item in retrieved}
    aggregate_context = [
        {
            "theme": item.get("theme"),
            "mention_count": item.get("mention_count"),
            "prevalence_pct": item.get("prevalence_pct"),
            "evidence_breadth": item.get("investigation", {}).get("evidence_breadth"),
        }
        for item in findings if item.get("theme") in retrieved_themes
    ]
    aggregate_json = json.dumps(aggregate_context, ensure_ascii=False)
    prompt = f"""Answer the user's customer-research question using only the dataset aggregates and retrieved records below.
Use aggregate mention counts and prevalence only for the named theme summaries provided; do not count the limited retrieved quotes as the full dataset.
Do not infer root causes, financial impact, severity, or product facts not present in the supplied data.
If the records do not answer the question, say what is missing.
Cite record IDs that directly support the answer. Use only IDs from the retrieved source records.
Return JSON only with this shape: {{"answer":"concise answer","record_ids":["FB-000001"],"caveat":"limitations or empty string"}}

Question: {question}
Dataset-level theme aggregates for retrieved themes:
{aggregate_json}
Retrieved source records:
{context}
"""
    try:
        response = model_call(prompt)
        answer = str(response.get("answer", "")).strip()
        cited_ids = response.get("record_ids", [])
        if not isinstance(cited_ids, list):
            cited_ids = []
        valid_ids = [str(value) for value in cited_ids if str(value) in source_ids]
        inline_ids = re.findall(r"\bFB-[A-Za-z0-9_-]+\b", answer)
        unsupported_inline_ids = [value for value in inline_ids if value not in source_ids]
        # Require at least one grounded citation and reject invented IDs in either
        # the machine-readable citation list or the answer prose.
        if not answer or not valid_ids or unsupported_inline_ids:
            raise OllamaError("The assistant response did not contain exclusively valid supporting record citations.")
        caveat = str(response.get("caveat", "")).strip()
        used_provider = str(response.get("_signaldesk_provider", active_provider()))
        method = ("qwen3_grounded" if OLLAMA_MODEL.casefold().startswith("qwen3") else "ollama_grounded") if used_provider == "ollama" else f"{used_provider}_grounded"
    except (OllamaError, ValueError, TypeError, AttributeError, KeyError):
        valid_ids = [item["record_id"] for item in retrieved[:5]]
        matching_themes = sorted({item["theme"] for item in retrieved if item["theme"]})
        answer = (
            f"I found {len(retrieved)} relevant source record(s) in this analysis, covering "
            f"{', '.join(matching_themes) or 'the retrieved feedback'}. Review the cited original comments below; "
            "I could not produce a validated AI synthesis for this question."
        )
        caveat = "Fallback answer: this response summarises retrieval results and does not infer a root cause."
        method = "retrieval_fallback"

    evidence_by_id = {item["record_id"]: item for item in retrieved}
    citations = [evidence_by_id[record_id] for record_id in dict.fromkeys(valid_ids)]
    return {
        "answer": answer,
        "cited_evidence": citations,
        "answer_method": method,
        "caveat": caveat,
    }
