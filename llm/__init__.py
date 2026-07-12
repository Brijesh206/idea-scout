"""Provider-agnostic LLM access. Nothing outside this package imports an LLM
SDK directly (see docs/04-llm-provider-interface.md)."""
from .provider import complete, model_label, active_provider

__all__ = ["complete", "model_label", "active_provider"]
