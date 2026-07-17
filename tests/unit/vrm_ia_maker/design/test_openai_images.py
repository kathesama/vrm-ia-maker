"""Network-free tests for the optional OpenAI image adapter."""

from __future__ import annotations

import base64
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from vrm_ia_maker.design.adapters.openai_images import OpenAIImageGenerator
from vrm_ia_maker.design.ports import (
    GenerationRequest,
    ImageGenerationConfigurationError,
    ImageGenerationError,
)

PNG_BYTES = b"\x89PNG\r\n\x1a\nprovider-result"
SECRET = "test-secret-that-must-not-leak"


def request(input_paths: tuple[Path, ...]) -> GenerationRequest:
    return GenerationRequest(
        task_id="face-turnaround",
        prompt_id="talking-bust.face-turnaround",
        prompt_version="1.0",
        prompt="Create one bounded technical reference candidate.",
        input_paths=input_paths,
        width=1536,
        height=1024,
    )


class FakeImages:
    def __init__(self, response: object | Exception) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def edit(self, **kwargs: Any) -> object:
        images = kwargs.pop("image")
        self.calls.append(
            {
                **kwargs,
                "input_names": [Path(image.name).name for image in images],
                "input_bytes": [image.read() for image in images],
            }
        )
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class FakeClient:
    def __init__(self, images: FakeImages) -> None:
        self.images = images


def make_adapter(
    response: object | Exception,
    *,
    model: str = "gpt-image-2",
) -> tuple[OpenAIImageGenerator, FakeImages, list[dict[str, Any]]]:
    images = FakeImages(response)
    constructor_calls: list[dict[str, Any]] = []

    def factory(**kwargs: Any) -> FakeClient:
        constructor_calls.append(kwargs)
        return FakeClient(images)

    adapter = OpenAIImageGenerator(
        model=model,
        timeout_seconds=17.0,
        environ={"OPENAI_API_KEY": SECRET},
        client_factory=factory,
    )
    return adapter, images, constructor_calls


def test_gpt_image_2_omits_unsupported_input_fidelity_without_sdk_retries(
    tmp_path: Path,
) -> None:
    master = tmp_path / "master.png"
    predecessor = tmp_path / "face.png"
    master.write_bytes(b"master")
    predecessor.write_bytes(b"approved predecessor")
    response = SimpleNamespace(
        data=[SimpleNamespace(b64_json=base64.b64encode(PNG_BYTES).decode("ascii"))]
    )
    adapter, images, constructor_calls = make_adapter(response)

    result = adapter.generate(request((master, predecessor)))

    assert result.data == PNG_BYTES
    assert result.provider == "openai"
    assert result.model == "gpt-image-2"
    assert constructor_calls == [
        {"api_key": SECRET, "max_retries": 0, "timeout": 17.0}
    ]
    assert len(images.calls) == 1
    assert images.calls[0] == {
        "model": "gpt-image-2",
        "prompt": "Create one bounded technical reference candidate.",
        "n": 1,
        "output_format": "png",
        "quality": "high",
        "size": "1536x1024",
        "timeout": 17.0,
        "input_names": ["master.png", "face.png"],
        "input_bytes": [b"master", b"approved predecessor"],
    }


def test_prior_gpt_image_model_requests_high_input_fidelity(tmp_path: Path) -> None:
    master = tmp_path / "master.png"
    master.write_bytes(b"master")
    response = SimpleNamespace(
        data=[SimpleNamespace(b64_json=base64.b64encode(PNG_BYTES).decode("ascii"))]
    )
    adapter, images, _ = make_adapter(response, model="gpt-image-1.5")

    adapter.generate(request((master,)))

    assert images.calls[0]["input_fidelity"] == "high"


def test_request_requires_at_least_one_approved_input() -> None:
    with pytest.raises(ValidationError, match="at least 1"):
        request(())


def test_adapter_rejects_missing_environment_credential(tmp_path: Path) -> None:
    source = tmp_path / "master.png"
    source.write_bytes(b"master")
    adapter = OpenAIImageGenerator(
        model="gpt-image-2",
        timeout_seconds=10.0,
        environ={},
        client_factory=lambda **_: object(),
    )

    with pytest.raises(ImageGenerationConfigurationError, match="OPENAI_API_KEY"):
        adapter.generate(request((source,)))


@pytest.mark.parametrize(
    "response",
    [
        SimpleNamespace(data=[]),
        SimpleNamespace(
            data=[
                SimpleNamespace(b64_json=base64.b64encode(PNG_BYTES).decode("ascii")),
                SimpleNamespace(b64_json=base64.b64encode(PNG_BYTES).decode("ascii")),
            ]
        ),
        SimpleNamespace(data=[SimpleNamespace(b64_json=None)]),
    ],
)
def test_adapter_requires_exactly_one_base64_image_payload(
    tmp_path: Path,
    response: object,
) -> None:
    source = tmp_path / "master.png"
    source.write_bytes(b"master")
    adapter, _, _ = make_adapter(response)

    with pytest.raises(ImageGenerationError, match="exactly one base64 image payload"):
        adapter.generate(request((source,)))


def test_adapter_rejects_malformed_base64(tmp_path: Path) -> None:
    source = tmp_path / "master.png"
    source.write_bytes(b"master")
    adapter, _, _ = make_adapter(
        SimpleNamespace(data=[SimpleNamespace(b64_json="not valid base64!")])
    )

    with pytest.raises(ImageGenerationError, match="malformed base64 image payload"):
        adapter.generate(request((source,)))


def test_provider_failure_is_sanitized_and_does_not_leak_secret(tmp_path: Path) -> None:
    source = tmp_path / "master.png"
    source.write_bytes(b"master")
    adapter, _, _ = make_adapter(RuntimeError(f"provider echoed {SECRET}"))

    with pytest.raises(ImageGenerationError) as caught:
        adapter.generate(request((source,)))

    assert caught.value.code == "provider_failure"
    assert str(caught.value) == "OpenAI image generation failed (RuntimeError)."
    assert SECRET not in str(caught.value)
    assert SECRET not in repr(adapter)


def test_provider_http_failure_exposes_only_safe_diagnostic_fields(tmp_path: Path) -> None:
    class FakeBadRequest(RuntimeError):
        status_code = 400
        body = {"code": "invalid_image", "message": f"echoed {SECRET}"}

    source = tmp_path / "master.png"
    source.write_bytes(b"master")
    adapter, _, _ = make_adapter(FakeBadRequest(f"remote message {SECRET}"))

    with pytest.raises(ImageGenerationError) as caught:
        adapter.generate(request((source,)))

    assert caught.value.code == "provider_failure"
    assert str(caught.value) == (
        "OpenAI image generation failed (FakeBadRequest, HTTP 400, code invalid_image)."
    )
    assert SECRET not in str(caught.value)


def test_moderation_failure_exposes_only_public_coarse_details(tmp_path: Path) -> None:
    class FakeModerationError(RuntimeError):
        status_code = 400
        body = {
            "code": "moderation_blocked",
            "message": f"echoed {SECRET}",
            "moderation_details": {
                "moderation_stage": "output",
                "categories": ["sexual", f"unsafe-{SECRET}"],
            },
        }

    source = tmp_path / "master.png"
    source.write_bytes(b"master")
    adapter, _, _ = make_adapter(FakeModerationError(f"remote message {SECRET}"))

    with pytest.raises(ImageGenerationError) as caught:
        adapter.generate(request((source,)))

    assert str(caught.value) == (
        "OpenAI image generation failed (FakeModerationError, HTTP 400, "
        "code moderation_blocked, stage output, categories sexual)."
    )
    assert SECRET not in str(caught.value)


def test_missing_optional_sdk_has_a_stable_configuration_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "master.png"
    source.write_bytes(b"master")
    monkeypatch.setitem(sys.modules, "openai", None)
    adapter = OpenAIImageGenerator(
        model="gpt-image-2",
        timeout_seconds=10.0,
        environ={"OPENAI_API_KEY": SECRET},
    )

    with pytest.raises(
        ImageGenerationConfigurationError,
        match="optional OpenAI dependency",
    ):
        adapter.generate(request((source,)))
