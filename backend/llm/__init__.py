"""LLM provider abstraction: API models (OpenAI-compatible, e.g. Groq) and local models (Ollama).

Use `get_llm()` to get an `LLMClient`, which adds retries, timeouts and per-call logging on top
of a provider.
"""
from llm.base import LLMError, LLMProvider, LLMResponse, StreamChunk, ToolCall
from llm.client import LLMClient, get_llm, set_llm_override

__all__ = ["LLMClient", "LLMError", "LLMProvider", "LLMResponse", "StreamChunk", "ToolCall",
           "get_llm", "set_llm_override"]
