"""Turn free-text project status updates into structured signals.

Stand-alone: it only needs the update text and the date it was written. Works with a
rule-based baseline (no API) or any OpenAI-compatible LLM endpoint (Gemini, Groq, Mistral,
Ollama, ...). Risk categories are configurable, so other PMOs can use their own.
"""

from .schema import Extraction, Risk

__all__ = ["Extraction", "Risk"]
