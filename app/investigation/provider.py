"""Replaceable provider protocol; no implicit live calls or provider retries."""
import json
from typing import Protocol
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from app.investigation.contracts import ModelTurn, Output, ToolCall

class ProviderError(RuntimeError):
    def __init__(self, code, transient=False):
        super().__init__(code)
        self.transient = transient

class ModelProvider(Protocol):
    identifier: str
    def turn(self, instructions, messages, tools, max_tokens) -> ModelTurn: ...

def strict_schema(schema):
    """OpenAI strict schemas require every property, including nullable fields."""
    if isinstance(schema, dict):
        converted = {key: strict_schema(value) for key, value in schema.items() if key != "default"}
        if "properties" in converted:
            converted["required"] = list(converted["properties"])
            converted["additionalProperties"] = False
        return converted
    if isinstance(schema, list):
        return [strict_schema(item) for item in schema]
    return schema

class OpenAIProvider:
    def __init__(self, settings, output_model=Output):
        if not (settings.investigator_live_enabled and settings.openai_api_key and
                settings.investigator_model and settings.investigator_model_version):
            raise ProviderError("provider_disabled")
        if min(settings.investigator_input_cost_per_million,
               settings.investigator_output_cost_per_million) <= 0:
            raise ProviderError("pricing_configuration_required")
        if settings.investigator_timeout_seconds >= settings.orchestration_lease_seconds / 2:
            raise ProviderError("provider_timeout_must_fit_lease")
        self.settings = settings
        self.output_model = output_model
        self.identifier = settings.investigator_model + ":" + settings.investigator_model_version

    def turn(self, instructions, messages, tools, max_tokens):
        body = {"model": self.settings.investigator_model, "instructions": instructions,
                "input": messages, "tools": [{**tool, "parameters": strict_schema(tool["parameters"]), "strict": True} for tool in tools], "store": False,
                "max_output_tokens": max_tokens,
                "text": {"format": {"type": "json_schema", "name": "investigation",
                    "strict": True, "schema": strict_schema(self.output_model.model_json_schema())}}}
        request = Request("https://api.openai.com/v1/responses", data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json",
                "Authorization": "Bearer " + self.settings.openai_api_key.get_secret_value()})
        try:
            with urlopen(request, timeout=self.settings.investigator_timeout_seconds) as response:
                raw = json.loads(response.read(2_000_001))
        except HTTPError as exc:
            raise ProviderError("provider_http_" + str(exc.code), exc.code in {408, 429} or exc.code >= 500) from None
        except (TimeoutError, URLError):
            raise ProviderError("provider_timeout_or_connection", True) from None
        if raw.get("status") not in {"completed", None}:
            raise ProviderError("provider_incomplete_response")
        calls, output = [], None
        for item in raw.get("output", []):
            if item.get("type") == "function_call":
                calls.append(ToolCall(name=item["name"], arguments=json.loads(item["arguments"]), call_id=item["call_id"]))
            if item.get("type") == "message":
                for content in item.get("content", []):
                    if content.get("type") == "output_text":
                        output = self.output_model.model_validate_json(content["text"])
        usage = raw.get("usage", {})
        return ModelTurn(calls=calls, output=output, input_tokens=usage.get("input_tokens", 0),
                         output_tokens=usage.get("output_tokens", 0))
