"""Tests for the bounded visual-reference authoring use case."""

from __future__ import annotations

import hashlib
import io
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PIL import Image

from vrm_ia_maker.design.adapters.filesystem import FilesystemAuthoringWorkspace
from vrm_ia_maker.design.contracts import (
    ApprovalDecision,
    ApprovalRecord,
    AuthoringState,
    CandidateStatus,
    GenerationAttempt,
    GenerationAttemptStatus,
    RightsMetadata,
    TaskProgress,
    TaskState,
)
from vrm_ia_maker.design.plan import TALKING_BUST_PLAN
from vrm_ia_maker.design.ports import (
    GeneratedImage,
    GenerationRequest,
    ImageGenerationError,
    WorkspaceInitialization,
)
from vrm_ia_maker.design.service import AuthoringService, AuthoringWorkflowError

NOW = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)


def png_bytes(size: tuple[int, int]) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (30, 60, 90)).save(buffer, format="PNG")
    return buffer.getvalue()


class FakeGenerator:
    def __init__(self, responses: list[GeneratedImage | ImageGenerationError]) -> None:
        self.responses = responses
        self.requests: list[GenerationRequest] = []

    def generate(self, request: GenerationRequest) -> GeneratedImage:
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, ImageGenerationError):
            raise response
        return response


class RequestSizedGenerator:
    def __init__(self) -> None:
        self.requests: list[GenerationRequest] = []

    def generate(self, request: GenerationRequest) -> GeneratedImage:
        self.requests.append(request)
        return generated((request.width, request.height))


def initialized_workspace(
    tmp_path: Path,
    *,
    complete_rights: bool = False,
) -> tuple[FilesystemAuthoringWorkspace, AuthoringState]:
    master = tmp_path / "master.png"
    master.write_bytes(png_bytes((1200, 1600)))
    workspace = FilesystemAuthoringWorkspace(tmp_path / "workspace")
    state = workspace.initialize(
        WorkspaceInitialization(
            master_source=master,
            package_id="juana-talking-bust",
            character_id="juana",
            display_name="Juana",
            revision="1.0.0",
            height_meters=1.70,
            authoritative_source="User-supplied repository concept sheet",
            rights=(
                RightsMetadata(
                    author="Katherine E. Aguirre",
                    rights_holder="Katherine E. Aguirre",
                    license="Author-approved project use",
                    commercial_use=True,
                    modification_allowed=True,
                    redistribution_allowed=True,
                    attribution="Katherine E. Aguirre / Juana IA",
                )
                if complete_rights
                else None
            ),
        )
    )
    return workspace, state


def generated(size: tuple[int, int] = (1536, 1024)) -> GeneratedImage:
    return GeneratedImage(data=png_bytes(size), provider="fake", model="fake-image-model")


def test_run_selects_one_task_and_persists_candidate_before_returning(tmp_path: Path) -> None:
    workspace, state = initialized_workspace(tmp_path)
    generator = FakeGenerator([generated()])
    service = AuthoringService(workspace=workspace, generator=generator, clock=lambda: NOW)

    result = service.run()

    assert result.task_id == "face-turnaround"
    assert result.attempt == 1
    assert result.candidate.candidate_id == "face-turnaround-attempt-1"
    assert len(generator.requests) == 1
    assert generator.requests[0].input_paths == (
        workspace.resolve_artifact(state.revision.master_reference.path),
    )
    restored = workspace.load_state()
    task = restored.tasks["face-turnaround"]
    assert task.progress is TaskProgress.CANDIDATE_READY
    assert task.attempts[0].status is GenerationAttemptStatus.CANDIDATE_READY
    assert task.candidates[0] == result.candidate


def test_pending_candidate_blocks_another_provider_request(tmp_path: Path) -> None:
    workspace, _ = initialized_workspace(tmp_path)
    generator = FakeGenerator([generated(), generated()])
    service = AuthoringService(workspace=workspace, generator=generator, clock=lambda: NOW)
    service.run()

    with pytest.raises(AuthoringWorkflowError) as caught:
        service.run()

    assert caught.value.code == "pending_review"
    assert len(generator.requests) == 1


def test_provider_failures_are_persisted_and_bounded_to_three_explicit_runs(
    tmp_path: Path,
) -> None:
    workspace, _ = initialized_workspace(tmp_path)
    generator = FakeGenerator(
        [
            ImageGenerationError("provider_failure", "Provider failed."),
            ImageGenerationError("provider_failure", "Provider failed."),
            ImageGenerationError("provider_failure", "Provider failed."),
        ]
    )
    service = AuthoringService(workspace=workspace, generator=generator, clock=lambda: NOW)

    for expected_attempt in (1, 2, 3):
        with pytest.raises(AuthoringWorkflowError) as caught:
            service.run()
        assert caught.value.code == "provider_failure"
        task = workspace.load_state().tasks["face-turnaround"]
        assert len(task.attempts) == expected_attempt
        assert task.attempts[-1].status is GenerationAttemptStatus.FAILED
        expected_progress = (
            TaskProgress.EXHAUSTED if expected_attempt == 3 else TaskProgress.RETRY_READY
        )
        assert task.progress is expected_progress

    with pytest.raises(AuthoringWorkflowError) as caught:
        service.run()
    assert caught.value.code == "attempts_exhausted"
    assert len(generator.requests) == 3


def test_invalid_candidate_is_an_auditable_failed_attempt(tmp_path: Path) -> None:
    workspace, _ = initialized_workspace(tmp_path)
    generator = FakeGenerator([generated((1024, 1024))])
    service = AuthoringService(workspace=workspace, generator=generator, clock=lambda: NOW)

    with pytest.raises(AuthoringWorkflowError) as caught:
        service.run()

    assert caught.value.code == "invalid_candidate"
    task = workspace.load_state().tasks["face-turnaround"]
    assert task.progress is TaskProgress.RETRY_READY
    assert task.attempts[0].error_code == "invalid_candidate"
    assert (
        workspace.root / "candidates/face-turnaround/attempt-1/failed-output.bin"
    ).is_file()


def test_interrupted_in_progress_attempt_is_failed_before_explicit_retry(
    tmp_path: Path,
) -> None:
    workspace, state = initialized_workspace(tmp_path)
    interrupted = GenerationAttempt(
        attempt_id="face-turnaround-attempt-1",
        task_id="face-turnaround",
        attempt=1,
        status=GenerationAttemptStatus.IN_PROGRESS,
        started_at=NOW,
        completed_at=None,
    )
    tasks = dict(state.tasks)
    tasks["face-turnaround"] = TaskState(
        task_id="face-turnaround",
        progress=TaskProgress.GENERATING,
        attempts=(interrupted,),
    )
    payload = state.model_dump(mode="json")
    payload["tasks"] = {
        task_id: task.model_dump(mode="json") for task_id, task in tasks.items()
    }
    workspace.save_state(AuthoringState.model_validate(payload))
    generator = FakeGenerator([generated()])
    service = AuthoringService(workspace=workspace, generator=generator, clock=lambda: NOW)

    result = service.run()

    assert result.attempt == 2
    restored = workspace.load_state().tasks["face-turnaround"]
    assert restored.attempts[0].status is GenerationAttemptStatus.FAILED
    assert restored.attempts[0].error_code == "interrupted_attempt"
    assert restored.attempts[1].status is GenerationAttemptStatus.CANDIDATE_READY
    assert len(generator.requests) == 1


def test_request_includes_master_and_only_approved_predecessor_sheets(
    tmp_path: Path,
) -> None:
    workspace, state = initialized_workspace(tmp_path)
    face_task = TALKING_BUST_PLAN.task("face-turnaround")
    candidate = workspace.stage_candidate(
        task=face_task,
        attempt=1,
        generated=generated(),
        input_artifacts=(state.revision.master_reference,),
        created_at=NOW,
    )
    candidate = candidate.model_copy(update={"status": CandidateStatus.APPROVED})
    approval = ApprovalRecord(
        approval_id="approve-face-turnaround-attempt-1",
        task_id="face-turnaround",
        candidate_id=candidate.candidate_id,
        decision=ApprovalDecision.APPROVE,
        approver="Kathy",
        decided_at=NOW,
        reviewed_artifacts=(
            candidate.sheet.path,
            *(preview.path for preview in candidate.previews),
        ),
        notes="Approved for the next bounded task.",
    )
    attempt = GenerationAttempt(
        attempt_id="face-turnaround-attempt-1",
        task_id="face-turnaround",
        attempt=1,
        status=GenerationAttemptStatus.CANDIDATE_READY,
        candidate_id=candidate.candidate_id,
        started_at=NOW,
        completed_at=NOW,
    )
    tasks = dict(state.tasks)
    tasks["face-turnaround"] = TaskState(
        task_id="face-turnaround",
        progress=TaskProgress.APPROVED,
        attempts=(attempt,),
        candidates=(candidate,),
        decisions=(approval,),
        approved_candidate_id=candidate.candidate_id,
    )
    payload = state.model_dump(mode="json")
    payload["tasks"] = {
        task_id: task.model_dump(mode="json") for task_id, task in tasks.items()
    }
    workspace.save_state(AuthoringState.model_validate(payload))
    generator = FakeGenerator([generated()])
    service = AuthoringService(workspace=workspace, generator=generator, clock=lambda: NOW)

    result = service.run()

    assert result.task_id == "facial-mechanics"
    assert generator.requests[0].input_paths == (
        workspace.resolve_artifact(state.revision.master_reference.path),
        workspace.resolve_artifact(candidate.sheet.path),
    )


@pytest.mark.parametrize("drift", ["plan_id", "tasks"])
def test_validate_rejects_persisted_plan_drift(tmp_path: Path, drift: str) -> None:
    workspace, state = initialized_workspace(tmp_path)
    payload = state.model_dump(mode="json")
    if drift == "plan_id":
        payload["plan_id"] = "unreviewed-plan"
    else:
        del payload["tasks"]["material-reference"]
    workspace.save_state(AuthoringState.model_validate(payload))
    service = AuthoringService(workspace=workspace, clock=lambda: NOW)

    with pytest.raises(AuthoringWorkflowError) as caught:
        service.validate()

    assert caught.value.code == "plan_mismatch"


def test_approve_records_full_review_scope_and_unlocks_the_next_task(tmp_path: Path) -> None:
    workspace, _ = initialized_workspace(tmp_path)
    generator = FakeGenerator([generated(), generated()])
    service = AuthoringService(workspace=workspace, generator=generator, clock=lambda: NOW)
    candidate = service.run().candidate

    approval = service.approve(
        task_id="face-turnaround",
        candidate_id=candidate.candidate_id,
        approver="Kathy",
        notes="Identity, views, and every crop are approved.",
    )

    assert set(approval.reviewed_artifacts) == {
        candidate.sheet.path,
        *(preview.path for preview in candidate.previews),
    }
    restored = workspace.load_state()
    task = restored.tasks["face-turnaround"]
    assert task.progress is TaskProgress.APPROVED
    assert task.candidates[0].status is CandidateStatus.APPROVED
    assert task.approved_candidate_id == candidate.candidate_id
    assert any(
        record.provenance_id == f"candidate-{candidate.candidate_id}"
        for record in restored.provenance
    )
    assert service.run().task_id == "facial-mechanics"


def test_reject_preserves_candidate_and_allows_the_next_explicit_attempt(
    tmp_path: Path,
) -> None:
    workspace, _ = initialized_workspace(tmp_path)
    generator = FakeGenerator([generated(), generated()])
    service = AuthoringService(workspace=workspace, generator=generator, clock=lambda: NOW)
    first = service.run().candidate
    sheet_path = workspace.resolve_artifact(first.sheet.path)
    sheet_hash = hashlib.sha256(sheet_path.read_bytes()).hexdigest()

    rejection = service.reject(
        task_id="face-turnaround",
        candidate_id=first.candidate_id,
        approver="Kathy",
        notes="The right profile does not preserve the approved hairstyle.",
    )

    assert rejection.decision is ApprovalDecision.REJECT
    rejected = workspace.load_state().tasks["face-turnaround"]
    assert rejected.progress is TaskProgress.RETRY_READY
    assert rejected.candidates[0].status is CandidateStatus.REJECTED
    assert hashlib.sha256(sheet_path.read_bytes()).hexdigest() == sheet_hash
    second = service.run()
    assert second.attempt == 2
    assert second.candidate.candidate_id == "face-turnaround-attempt-2"


def test_candidate_cannot_receive_a_second_decision(tmp_path: Path) -> None:
    workspace, _ = initialized_workspace(tmp_path)
    service = AuthoringService(
        workspace=workspace,
        generator=FakeGenerator([generated()]),
        clock=lambda: NOW,
    )
    candidate = service.run().candidate
    service.approve(
        task_id="face-turnaround",
        candidate_id=candidate.candidate_id,
        approver="Kathy",
        notes="Approved after reviewing every artifact.",
    )

    with pytest.raises(AuthoringWorkflowError) as caught:
        service.reject(
            task_id="face-turnaround",
            candidate_id=candidate.candidate_id,
            approver="Kathy",
            notes="Conflicting second decision.",
        )

    assert caught.value.code == "decision_conflict"


def test_supersede_preserves_approval_and_reopens_the_task(tmp_path: Path) -> None:
    workspace, _ = initialized_workspace(tmp_path)
    generator = FakeGenerator([generated(), generated()])
    service = AuthoringService(workspace=workspace, generator=generator, clock=lambda: NOW)
    first = service.run().candidate
    service.approve(
        task_id="face-turnaround",
        candidate_id=first.candidate_id,
        approver="Kathy",
        notes="Approved before the canonical direction changed.",
    )

    supersession = service.supersede(
        task_id="face-turnaround",
        candidate_id=first.candidate_id,
        approver="Kathy",
        notes="Superseded by a corrected canonical direction.",
    )

    assert supersession.decision is ApprovalDecision.SUPERSEDE
    reopened = workspace.load_state().tasks["face-turnaround"]
    assert reopened.progress is TaskProgress.RETRY_READY
    assert reopened.approved_candidate_id is None
    assert reopened.candidates[0].status is CandidateStatus.SUPERSEDED
    assert tuple(decision.decision for decision in reopened.decisions) == (
        ApprovalDecision.APPROVE,
        ApprovalDecision.SUPERSEDE,
    )
    assert service.run().attempt == 2


def test_supersede_requires_dependent_candidates_to_be_resolved(tmp_path: Path) -> None:
    workspace, _ = initialized_workspace(tmp_path)
    generator = FakeGenerator([generated(), generated()])
    service = AuthoringService(workspace=workspace, generator=generator, clock=lambda: NOW)
    face = service.run().candidate
    service.approve(
        task_id="face-turnaround",
        candidate_id=face.candidate_id,
        approver="Kathy",
        notes="Approved every face artifact.",
    )
    service.run()

    with pytest.raises(AuthoringWorkflowError) as caught:
        service.supersede(
            task_id="face-turnaround",
            candidate_id=face.candidate_id,
            approver="Kathy",
            notes="A dependent candidate is still pending review.",
        )

    assert caught.value.code == "dependent_review_required"


def test_set_rights_completes_master_provenance_and_clears_its_gap(
    tmp_path: Path,
) -> None:
    workspace, _ = initialized_workspace(tmp_path)
    service = AuthoringService(workspace=workspace, clock=lambda: NOW)
    rights = RightsMetadata(
        author="Katherine E. Aguirre",
        rights_holder="Katherine E. Aguirre",
        license="Author-approved project use",
        commercial_use=True,
        modification_allowed=True,
        redistribution_allowed=True,
        attribution="Katherine E. Aguirre / Juana IA",
    )

    master = service.set_rights(
        rights,
        authoritative_source=(
            "OpenAI ChatGPT image generation directed by Katherine E. Aguirre."
        ),
    )

    assert master.provenance_id == "master-reference"
    assert master.rights == rights
    assert master.authoritative_source == (
        "OpenAI ChatGPT image generation directed by Katherine E. Aguirre."
    )
    state = workspace.load_state()
    assert state.provenance[0].rights == rights
    assert "source-rights-incomplete" not in {gap.gap_id for gap in state.gaps}
    assert "measurements-missing" in {gap.gap_id for gap in state.gaps}


def test_set_rights_rejects_incomplete_metadata(tmp_path: Path) -> None:
    workspace, _ = initialized_workspace(tmp_path)
    service = AuthoringService(workspace=workspace, clock=lambda: NOW)

    with pytest.raises(AuthoringWorkflowError) as incomplete:
        service.set_rights(
            RightsMetadata(author="Katherine E. Aguirre"),
            authoritative_source="OpenAI ChatGPT image generation.",
        )
    assert incomplete.value.code == "incomplete_rights"


def test_set_rights_rejects_overwriting_complete_metadata(tmp_path: Path) -> None:
    workspace, _ = initialized_workspace(tmp_path, complete_rights=True)
    service = AuthoringService(workspace=workspace, clock=lambda: NOW)

    with pytest.raises(AuthoringWorkflowError) as duplicate:
        service.set_rights(
            RightsMetadata(
                author="Katherine E. Aguirre",
                rights_holder="Katherine E. Aguirre",
                license="Author-approved project use",
                commercial_use=True,
                modification_allowed=True,
                redistribution_allowed=True,
                attribution="Katherine E. Aguirre / Juana IA",
            ),
            authoritative_source="OpenAI ChatGPT image generation.",
        )
    assert duplicate.value.code == "rights_already_complete"


def test_set_rights_rejects_a_blank_authoritative_source(tmp_path: Path) -> None:
    workspace, _ = initialized_workspace(tmp_path)
    service = AuthoringService(workspace=workspace, clock=lambda: NOW)
    rights = RightsMetadata(
        author="Katherine E. Aguirre",
        rights_holder="Katherine E. Aguirre",
        license="Proprietary project use",
        commercial_use=True,
        modification_allowed=True,
        redistribution_allowed=True,
        attribution="Katherine E. Aguirre / Juana IA",
    )

    with pytest.raises(AuthoringWorkflowError) as caught:
        service.set_rights(rights, authoritative_source="   ")

    assert caught.value.code == "invalid_authoritative_source"


def approve_all_tasks(service: AuthoringService) -> None:
    for expected_task in TALKING_BUST_PLAN.tasks:
        result = service.run()
        assert result.task_id == expected_task.task_id
        service.approve(
            task_id=result.task_id,
            candidate_id=result.candidate.candidate_id,
            approver="Kathy",
            notes=f"Approved every artifact for {result.task_id}.",
        )


def test_seal_requires_every_visual_task_to_be_approved(tmp_path: Path) -> None:
    workspace, _ = initialized_workspace(tmp_path, complete_rights=True)
    service = AuthoringService(
        workspace=workspace,
        generator=RequestSizedGenerator(),
        clock=lambda: NOW,
    )

    with pytest.raises(AuthoringWorkflowError) as caught:
        service.seal(tmp_path / "package")

    assert caught.value.code == "incomplete_authoring"
    assert not (tmp_path / "package").exists()


def test_seal_blocks_incomplete_source_rights_after_visual_approval(tmp_path: Path) -> None:
    workspace, _ = initialized_workspace(tmp_path)
    service = AuthoringService(
        workspace=workspace,
        generator=RequestSizedGenerator(),
        clock=lambda: NOW,
    )
    approve_all_tasks(service)

    with pytest.raises(AuthoringWorkflowError) as caught:
        service.seal(tmp_path / "package")

    assert caught.value.code == "blocking_gap"
    assert "source-rights-incomplete" in str(caught.value)
    assert not (tmp_path / "package").exists()


def test_seal_publishes_a_valid_no_clobber_character_design_package(
    tmp_path: Path,
) -> None:
    workspace, _ = initialized_workspace(tmp_path, complete_rights=True)
    generator = RequestSizedGenerator()
    service = AuthoringService(workspace=workspace, generator=generator, clock=lambda: NOW)
    approve_all_tasks(service)
    destination = tmp_path / "character-design-package"

    evidence = service.seal(destination)

    assert destination.is_dir()
    assert (destination / "package.json").is_file()
    assert (destination / "provenance.json").is_file()
    assert (destination / "approvals.json").is_file()
    assert (destination / "gaps.json").is_file()
    assert (destination / "references/master/master-character-sheet.png").is_file()
    assert (destination / "assets/base").is_dir()
    assert (destination / "assets/hair").is_dir()
    assert (destination / "assets/outfit").is_dir()
    assert (destination / "assets/accessories").is_dir()
    assert (destination / "adapters").is_dir()
    for task in TALKING_BUST_PLAN.tasks:
        assert (
            destination / f"references/master/approved-sheets/{task.task_id}.png"
        ).is_file()
        for panel in task.panels:
            assert (destination / panel.package_path).is_file()

    package = json.loads((destination / "package.json").read_text(encoding="utf-8"))
    approvals = json.loads((destination / "approvals.json").read_text(encoding="utf-8"))
    provenance = json.loads((destination / "provenance.json").read_text(encoding="utf-8"))
    assert package["package_id"] == "juana-talking-bust"
    assert package["required_expressions"] == [
        "blink",
        "blinkLeft",
        "blinkRight",
        "happy",
        "sad",
        "angry",
        "surprised",
        "relaxed",
    ]
    assert package["required_visemes"] == ["aa", "ih", "ou", "ee", "oh"]
    assert len(approvals["approvals"]) == 8
    expected_provenance_records = 1 + len(TALKING_BUST_PLAN.tasks) + sum(
        len(task.panels) for task in TALKING_BUST_PLAN.tasks
    )
    assert len(provenance["records"]) == expected_provenance_records
    assert evidence == workspace.validate_sealed_package(destination)
    for relative_path, digest in evidence.file_hashes.items():
        assert hashlib.sha256((destination / relative_path).read_bytes()).hexdigest() == digest

    sentinel = destination / "sentinel.txt"
    sentinel.write_text("keep", encoding="utf-8")
    with pytest.raises(AuthoringWorkflowError) as caught:
        service.seal(destination)
    assert caught.value.code == "destination_exists"
    assert sentinel.read_text(encoding="utf-8") == "keep"

    approved_face = workspace.load_state().tasks["face-turnaround"].candidates[0]
    workspace.resolve_artifact(approved_face.previews[0].path).write_bytes(b"tampered")
    tampered_destination = tmp_path / "tampered-package"
    with pytest.raises(AuthoringWorkflowError) as caught:
        service.seal(tampered_destination)
    assert caught.value.code == "integrity_failure"
    assert not tampered_destination.exists()
