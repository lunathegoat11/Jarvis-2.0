"""Picking a model that the provider actually offers today.

Hosted providers retire models (NVIDIA dropped Llama 3.3 70B in 2026), so
instead of trusting a fixed name Jarvis asks the provider for its current
list at startup and takes the first match from these preferences. Models
that answer straight away come before ones that think first, because a
voice assistant has to feel quick.
"""

import re

PREFERENCES = {
    "nvidia": {
        # Needs tool calling for Command mode.
        "text": [
            r"^meta/llama-4-maverick",
            r"^meta/llama-3\.3-70b-instruct$",
            r"^qwen/qwen3[\w.-]*-instruct",
            r"^openai/gpt-oss-120b$",
            r"^nvidia/nemotron-3-super",
            r"^nvidia/llama-3\.3-nemotron-super",
            r"^nvidia/nemotron-3-ultra",
            r"^z-ai/glm",
            r"^mistralai/mistral-(medium|large)",
        ],
        # Needs to read images for Ask mode.
        "vision": [
            r"^meta/llama-4-maverick",
            r"^meta/llama-4-scout",
            r"^meta/llama-3\.2-90b-vision-instruct$",
            r"^qwen/qwen[\w.-]*-vl",
            r"^z-ai/glm[\w.-]*(flash|v)",
            r"^google/gemma-3",
            r"^microsoft/phi-4-multimodal",
            r"^nvidia/[\w.-]*nemotron[\w.-]*-vl",
            r"^meta/llama-3\.2-11b-vision-instruct$",
        ],
    },
}


def pick(available: list[str], preferences: list[str]) -> str | None:
    """First available model matching the earliest preference, or None."""
    for pattern in preferences:
        regex = re.compile(pattern)
        matches = sorted(m for m in available if regex.search(m))
        if matches:
            return matches[0]
    return None


def list_models(client) -> list[str]:
    return sorted(m.id for m in client.models.list())
