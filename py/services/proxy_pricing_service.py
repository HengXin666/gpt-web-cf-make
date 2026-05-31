"""Proxy token accounting and OpenAI price estimates."""

from __future__ import annotations

from typing import Any


TEXT_PRICES_PER_M = {
    "gpt-5.5": {"input": 5.0, "cached": 0.50, "output": 30.0},
    "gpt-5.4-mini": {"input": 0.75, "cached": 0.075, "output": 4.50},
    "gpt-5.4": {"input": 2.50, "cached": 0.25, "output": 15.0},
    "gpt-5.2-pro": {"input": 21.0, "cached": 21.0, "output": 168.0},
    "gpt-5.2": {"input": 1.75, "cached": 0.175, "output": 14.0},
    "gpt-5-pro": {"input": 15.0, "cached": 15.0, "output": 120.0},
    "gpt-5.1": {"input": 1.25, "cached": 0.125, "output": 10.0},
    "gpt-5-mini": {"input": 0.25, "cached": 0.025, "output": 2.0},
    "gpt-5-nano": {"input": 0.05, "cached": 0.005, "output": 0.40},
    "gpt-5": {"input": 1.25, "cached": 0.125, "output": 10.0},
    "gpt-4.1-mini": {"input": 0.40, "cached": 0.10, "output": 1.60},
    "gpt-4.1-nano": {"input": 0.10, "cached": 0.025, "output": 0.40},
    "gpt-4.1": {"input": 2.0, "cached": 0.50, "output": 8.0},
    "gpt-4o-mini": {"input": 0.15, "cached": 0.075, "output": 0.60},
    "gpt-4o": {"input": 2.50, "cached": 1.25, "output": 10.0},
}

IMAGE_PRICES_PER_M = {
    "gpt-image-1.5": {"text_input": 5.0, "text_cached": 1.25, "image_input": 8.0, "image_cached": 2.0, "image_output": 32.0},
    "gpt-image-2": {"text_input": 5.0, "text_cached": 1.25, "image_input": 8.0, "image_cached": 2.0, "image_output": 30.0},
    "chatgpt-image-latest": {"text_input": 5.0, "text_cached": 1.25, "image_input": 8.0, "image_cached": 2.0, "image_output": 32.0},
    "gpt-image-1": {"text_input": 5.0, "text_cached": 1.25, "image_input": 10.0, "image_cached": 2.50, "image_output": 40.0},
    "gpt-image-1-mini": {"text_input": 2.0, "text_cached": 0.20, "image_input": 2.50, "image_cached": 0.25, "image_output": 8.0},
}

DEFAULT_IMAGE_OUTPUT_TOKENS = 1333
DEFAULT_IMAGE_INPUT_TOKENS = 1000


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _model_price(model: str) -> tuple[str, dict[str, float]]:
    name = str(model or "").strip().lower()
    for key in sorted(TEXT_PRICES_PER_M, key=len, reverse=True):
        if name.startswith(key):
            return key, TEXT_PRICES_PER_M[key]
    return "gpt-5", TEXT_PRICES_PER_M["gpt-5"]


def _image_price(model: str) -> tuple[str, dict[str, float]]:
    name = str(model or "").strip().lower()
    for key in sorted(IMAGE_PRICES_PER_M, key=len, reverse=True):
        if name.startswith(key):
            return key, IMAGE_PRICES_PER_M[key]
    return "gpt-image-2", IMAGE_PRICES_PER_M["gpt-image-2"]


def compute_usage_cost(entry: dict[str, Any]) -> dict[str, Any]:
    usage = entry.get("usage") if isinstance(entry.get("usage"), dict) else {}
    model = str(entry.get("model") or "")
    path = str(entry.get("path") or "")
    input_tokens = _int(usage.get("prompt_tokens") or usage.get("input_tokens"))
    cached_input_tokens = _int(usage.get("cached_tokens") or usage.get("cached_input_tokens"))
    output_tokens = _int(usage.get("completion_tokens") or usage.get("output_tokens"))
    image_input_tokens = _int(usage.get("image_input_tokens"))
    image_output_tokens = _int(usage.get("image_output_tokens"))
    image_count = _int(usage.get("image_count"))
    estimated = bool(usage.get("estimated"))

    if "image" in model.lower() or "/images/" in path:
        price_model, rates = _image_price(model)
        if image_count and not image_output_tokens:
            image_output_tokens = image_count * DEFAULT_IMAGE_OUTPUT_TOKENS
            estimated = True
        input_cost = input_tokens * rates["text_input"] / 1_000_000
        cached_cost = cached_input_tokens * rates["text_cached"] / 1_000_000
        output_cost = output_tokens * rates["text_input"] / 1_000_000
        image_input_cost = image_input_tokens * rates["image_input"] / 1_000_000
        image_output_cost = image_output_tokens * rates["image_output"] / 1_000_000
    else:
        price_model, rates = _model_price(model)
        billable_input_tokens = max(0, input_tokens - cached_input_tokens)
        input_cost = billable_input_tokens * rates["input"] / 1_000_000
        cached_cost = cached_input_tokens * rates["cached"] / 1_000_000
        output_cost = output_tokens * rates["output"] / 1_000_000
        image_input_cost = 0.0
        image_output_cost = 0.0

    total_cost = input_cost + cached_cost + output_cost + image_input_cost + image_output_cost
    return {
        "pricing_model": price_model,
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_input_tokens,
        "output_tokens": output_tokens,
        "image_input_tokens": image_input_tokens,
        "image_output_tokens": image_output_tokens,
        "image_count": image_count,
        "estimated": estimated,
        "input_cost_usd": round(input_cost, 8),
        "cached_input_cost_usd": round(cached_cost, 8),
        "output_cost_usd": round(output_cost, 8),
        "image_input_cost_usd": round(image_input_cost, 8),
        "image_output_cost_usd": round(image_output_cost, 8),
        "total_cost_usd": round(total_cost, 8),
    }
