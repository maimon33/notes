import json
import urllib.error
import urllib.request
from dataclasses import dataclass


PROVIDERS = ("anthropic", "openai", "gemini", "xai")

DEFAULT_MODELS = {
    "anthropic": "claude-haiku-4-5",
    "openai": "gpt-5-mini",
    "gemini": "gemini-2.0-flash",
    "xai": "grok-4.3",
}

ENV_TOKEN_MAP = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "xai": "XAI_API_KEY",
}


@dataclass
class RuntimeSettings:
    provider: str | None
    tokens: dict[str, str]
    models: dict[str, str]


def merge_settings(cfg, stored: dict | None) -> RuntimeSettings:
    stored = stored or {}
    tokens = {}
    models = {}
    for provider in PROVIDERS:
        token = (stored.get(f"{provider}_api_key") or getattr(cfg, f"{provider}_api_key", None) or "").strip()
        model = (stored.get(f"{provider}_model") or getattr(cfg, f"{provider}_model", None) or DEFAULT_MODELS[provider]).strip()
        if token:
            tokens[provider] = token
        models[provider] = model or DEFAULT_MODELS[provider]
    selected = (stored.get("ai_provider") or getattr(cfg, "ai_provider", None) or "").strip().lower()
    provider = resolve_provider(selected, tokens)
    return RuntimeSettings(provider=provider, tokens=tokens, models=models)


def resolve_provider(selected: str | None, tokens: dict[str, str]) -> str | None:
    if selected in PROVIDERS and tokens.get(selected):
        return selected
    for provider in PROVIDERS:
        if tokens.get(provider):
            return provider
    return None


def provider_label(provider: str | None) -> str:
    labels = {
        "anthropic": "Anthropic",
        "openai": "OpenAI",
        "gemini": "Gemini",
        "xai": "xAI / Grok",
    }
    return labels.get(provider or "", "None")


def configured_providers(runtime: RuntimeSettings) -> list[str]:
    return [provider for provider in PROVIDERS if runtime.tokens.get(provider)]


def generate_json(runtime: RuntimeSettings, system: str, user: str) -> dict:
    if not runtime.provider:
        raise RuntimeError("No AI provider configured")
    provider = runtime.provider
    token = runtime.tokens[provider]
    model = runtime.models[provider]
    prompt = (
        f"{system}\n\n"
        "Return only valid JSON. Do not wrap it in markdown fences.\n\n"
        f"{user}"
    )
    if provider == "anthropic":
        text = _anthropic_text(token, model, system, user)
    elif provider == "openai":
        text = _responses_text("https://api.openai.com/v1/responses", token, model, prompt)
    elif provider == "xai":
        text = _responses_text("https://api.x.ai/v1/responses", token, model, prompt)
    elif provider == "gemini":
        text = _gemini_text(token, model, system, user)
    else:
        raise RuntimeError(f"Unsupported AI provider: {provider}")
    return _parse_json_text(text)


def _post_json(url: str, payload: dict, headers: dict[str, str], timeout: int = 45) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{exc.code} from AI provider: {body[:280]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"AI provider request failed: {exc.reason}") from exc


def _responses_text(url: str, token: str, model: str, prompt: str) -> str:
    data = _post_json(
        url,
        {"model": model, "input": prompt},
        {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    text = data.get("output_text")
    if text:
        return text
    for item in data.get("output", []):
        for block in item.get("content", []):
            if isinstance(block, dict) and block.get("type") in {"output_text", "text"} and block.get("text"):
                return block["text"]
    raise RuntimeError("AI provider returned no text output")


def _anthropic_text(token: str, model: str, system: str, user: str) -> str:
    data = _post_json(
        "https://api.anthropic.com/v1/messages",
        {
            "model": model,
            "max_tokens": 700,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        },
        {
            "x-api-key": token,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )
    for block in data.get("content", []):
        if block.get("type") == "text" and block.get("text"):
            return block["text"]
    raise RuntimeError("Anthropic returned no text output")


def _gemini_text(token: str, model: str, system: str, user: str) -> str:
    model_name = model if model.startswith("models/") else f"models/{model}"
    data = _post_json(
        f"https://generativelanguage.googleapis.com/v1beta/{model_name}:generateContent?key={token}",
        {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"parts": [{"text": user}]}],
        },
        {"Content-Type": "application/json"},
    )
    for candidate in data.get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            if part.get("text"):
                return part["text"]
    raise RuntimeError("Gemini returned no text output")


def _parse_json_text(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3:
            text = "\n".join(lines[1:-1]).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start:end + 1])
        raise RuntimeError("AI provider returned invalid JSON")
