"""Generation subpackage — Claude Sonnet 4.6 + structured citations.

Houses the LangGraph ``generation_node`` (T041) that grounds the answer
in the retrieved chunks and emits inline ``[N]`` citation markers
matching a structured citation list.
"""

from .generation_node import GenerationNode

__all__ = ["GenerationNode"]
