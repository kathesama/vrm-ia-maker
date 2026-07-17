"""Optional OpenAI image-generation adapter for build-time authoring."""

from __future__ import annotations

import base64
import binascii
import os
import re
from collections.abc import Callable, Mapping
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from vrm_ia_maker.design.ports import (
    GeneratedImage,
    GenerationRequest,
    ImageGenerationConfigurationError,
    ImageGenerationError,
)

ClientFactory = Callable[..., Any]
_SAFE_PROVIDER_CODE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_PUBLIC_MODERATION_CATEGORIES = frozenset(
    {"harassment", "self-harm", "sexual", "violence"}
)
_PUBLIC_MODERATION_STAGES = frozenset({"input", "output", "unknown"})


class OpenAIImageGenerator:
    """Translate a bounded request into one OpenAI Images edit call."""

    def __init__(
        self,
        *,
        model: str,
        timeout_seconds: float,
        environ: Mapping[str, str] | None = None,
        client_factory: ClientFactory | None = None,
    ) -> None:
        if not model:
            raise ValueError("OpenAI image model must not be empty.")
        if timeout_seconds <= 0:
            raise ValueError("OpenAI timeout_seconds must be positive.")
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._environ = os.environ if environ is None else environ
        self._client_factory = client_factory

    def generate(self, request: GenerationRequest) -> GeneratedImage:
        """Issue one request with explicit timeout and no transparent retries."""
        api_key = self._environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise ImageGenerationConfigurationError(
                "missing_credential",
                "OPENAI_API_KEY is required for the OpenAI image adapter.",
            )

        client = self._create_client(api_key)
        try:
            with ExitStack() as stack:
                image_files = [
                    stack.enter_context(Path(path).open("rb")) for path in request.input_paths
                ]
                edit_options: dict[str, Any] = {
                    "model": self._model,
                    "image": image_files,
                    "prompt": request.prompt,
                    "n": 1,
                    "output_format": "png",
                    "quality": "high",
                    "size": f"{request.width}x{request.height}",
                    "timeout": self._timeout_seconds,
                }
                if self._model != "gpt-image-2":
                    edit_options["input_fidelity"] = "high"
                response = client.images.edit(**edit_options)
        except OSError as exc:
            raise ImageGenerationError(
                "input_unavailable",
                "An approved input image is unavailable.",
            ) from exc
        except Exception as exc:
            raise self._provider_failure(exc) from exc

        data = getattr(response, "data", None)
        if not isinstance(data, list | tuple) or len(data) != 1:
            raise ImageGenerationError(
                "invalid_provider_output",
                "OpenAI must return exactly one base64 image payload.",
            )
        payload = getattr(data[0], "b64_json", None)
        if not isinstance(payload, str) or not payload:
            raise ImageGenerationError(
                "invalid_provider_output",
                "OpenAI must return exactly one base64 image payload.",
            )
        try:
            image_data = base64.b64decode(payload, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ImageGenerationError(
                "invalid_provider_output",
                "OpenAI returned a malformed base64 image payload.",
            ) from exc
        if not image_data:
            raise ImageGenerationError(
                "invalid_provider_output",
                "OpenAI returned a malformed base64 image payload.",
            )
        return GeneratedImage(data=image_data, provider="openai", model=self._model)

    def _create_client(self, api_key: str) -> Any:
        if self._client_factory is not None:
            factory = self._client_factory
        else:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise ImageGenerationConfigurationError(
                    "missing_dependency",
                    "Install the optional OpenAI dependency to use this adapter.",
                ) from exc
            factory = OpenAI
        try:
            return factory(
                api_key=api_key,
                max_retries=0,
                timeout=self._timeout_seconds,
            )
        except ImageGenerationConfigurationError:
            raise
        except Exception as exc:
            raise self._provider_failure(exc) from exc

    @staticmethod
    def _provider_failure(exc: Exception) -> ImageGenerationError:
        details = [type(exc).__name__]
        status_code = getattr(exc, "status_code", None)
        if isinstance(status_code, int) and 100 <= status_code <= 599:
            details.append(f"HTTP {status_code}")
        body = getattr(exc, "body", None)
        provider_code = None
        nested_error = None
        if isinstance(body, Mapping):
            provider_code = body.get("code")
            nested_error = body.get("error")
            if provider_code is None and isinstance(nested_error, Mapping):
                provider_code = nested_error.get("code")
        if isinstance(provider_code, str) and _SAFE_PROVIDER_CODE.fullmatch(provider_code):
            details.append(f"code {provider_code}")
        moderation_details = body.get("moderation_details") if isinstance(body, Mapping) else None
        if moderation_details is None and isinstance(nested_error, Mapping):
            moderation_details = nested_error.get("moderation_details")
        if provider_code == "moderation_blocked" and isinstance(moderation_details, Mapping):
            stage = moderation_details.get("moderation_stage")
            if stage in _PUBLIC_MODERATION_STAGES:
                details.append(f"stage {stage}")
            categories = moderation_details.get("categories")
            if isinstance(categories, list | tuple):
                public_categories = [
                    category
                    for category in categories
                    if category in _PUBLIC_MODERATION_CATEGORIES
                ]
                if public_categories:
                    details.append(f"categories {', '.join(public_categories)}")
        diagnostic = ", ".join(details)
        return ImageGenerationError(
            "provider_failure",
            f"OpenAI image generation failed ({diagnostic}).",
        )
