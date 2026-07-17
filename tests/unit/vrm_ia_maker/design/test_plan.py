"""Tests for the fixed talking-bust reference-authoring plan."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from vrm_ia_maker.design.plan import (
    TALKING_BUST_PLAN,
    AuthoringPlanDefinition,
)

EXPECTED_TASK_IDS = (
    "face-turnaround",
    "facial-mechanics",
    "upper-body-turnaround",
    "expressions",
    "visemes",
    "hair-construction",
    "outfit-construction",
    "material-reference",
)


def test_talking_bust_plan_has_exactly_eight_tasks_in_stable_order() -> None:
    assert tuple(task.task_id for task in TALKING_BUST_PLAN.tasks) == EXPECTED_TASK_IDS


def test_every_task_has_a_versioned_bounded_png_request() -> None:
    for index, task in enumerate(TALKING_BUST_PLAN.tasks):
        assert task.order == index
        assert task.prompt_id == f"talking-bust.{task.task_id}"
        expected_prompt_version = {
            "face-turnaround": "1.2",
            "facial-mechanics": "1.1",
            "upper-body-turnaround": "1.2",
            "visemes": "1.2",
            "hair-construction": "1.1",
            "outfit-construction": "1.4",
            "material-reference": "1.3",
        }.get(task.task_id, "1.0")
        assert task.prompt_version == expected_prompt_version
        assert task.include_master is True
        assert task.output_format == "png"
        assert task.max_attempts == 3
        assert task.width % task.columns == 0
        assert task.height % task.rows == 0
        assert "technical reference candidate" in task.prompt.lower()
        assert "no text" in task.prompt.lower()


def test_face_prompt_limits_output_to_an_adult_head_and_neck_reference() -> None:
    prompt = TALKING_BUST_PLAN.task("face-turnaround").prompt.lower()

    assert "depicted character is an adult" in prompt
    assert "frame only the head and neck" in prompt
    assert "exclude the chest and torso" in prompt


def test_face_prompt_preserves_asymmetric_hair_across_opposite_profiles() -> None:
    prompt = TALKING_BUST_PLAN.task("face-turnaround").prompt.lower()

    assert "left-profile panel must show the shaved temple and visible ear" in prompt
    assert "right-profile panel must show the opposite side" in prompt
    assert "long swept hair must cover the right temple and ear" in prompt
    assert "must not mirror or repeat the shaved side" in prompt


def test_facial_mechanics_prompt_maps_blinks_to_anatomical_eyes() -> None:
    prompt = TALKING_BUST_PLAN.task("facial-mechanics").prompt.lower()

    assert "blink-left panel must close only the character's anatomical left eye" in prompt
    assert "appears on the viewer's right beside the shaved temple" in prompt
    assert "blink-right panel must close only the character's anatomical right eye" in prompt
    assert "appears on the viewer's left beneath the long hair" in prompt
    assert "do not duplicate the same closed eye" in prompt


def test_upper_body_prompt_uses_a_neutral_covered_talking_bust_frame() -> None:
    prompt = TALKING_BUST_PLAN.task("upper-body-turnaround").prompt.lower()

    assert "depicted character is an adult" in prompt
    assert "frame from the top of the head through the upper torso only" in prompt
    assert "crop above the waist" in prompt
    assert "fully closed high-neck white technical suit" in prompt
    assert "continuous opaque coverage" in prompt
    assert "keep the chest, waist, and pose neutral and unaccentuated" in prompt
    assert "treat left and right as the character's anatomical sides" in prompt
    assert "preserve the approved asymmetric hairstyle in every view" in prompt
    assert "top-right left-side panel must expose the shaved left temple and ear" in prompt
    assert "bottom-left right-side panel must show the opposite side" in prompt
    assert "long swept hair covering the right temple and ear" in prompt
    assert "must not mirror or repeat the shaved side" in prompt


def test_viseme_prompt_keeps_ih_and_ee_relaxed_and_emotionally_neutral() -> None:
    prompt = TALKING_BUST_PLAN.task("visemes").prompt.lower()

    assert "ih must be a natural, relaxed i articulation" in prompt
    assert "gently spread lips and a narrow horizontal opening" in prompt
    assert "without stretching or clenching the lip corners" in prompt
    assert "keep the jaw and cheeks relaxed" in prompt
    assert "no grimace, anger, or smile" in prompt
    assert "ee must use a soft, moderately open articulation" in prompt
    assert "not a broad toothy smile" in prompt
    assert "keep neutral, aa, ou, and oh unchanged" in prompt


def test_hair_prompt_preserves_asymmetry_in_every_construction_view() -> None:
    prompt = TALKING_BUST_PLAN.task("hair-construction").prompt.lower()

    assert "treat left and right as the character's anatomical sides" in prompt
    assert "top-middle left-side panel must expose the shaved left temple and ear" in prompt
    assert "top-right right-side panel must show the opposite side" in prompt
    assert "long swept hair covering the right temple and ear" in prompt
    assert "bottom-left back, bottom-middle top, and bottom-right hairline panels" in prompt
    assert "left undercut boundary and right-side long-hair root" in prompt
    assert "must not mirror or repeat the shaved side" in prompt
    assert "must not symmetrize the hairstyle" in prompt


def test_outfit_prompt_preserves_the_canonical_open_zip_construction() -> None:
    prompt = TALKING_BUST_PLAN.task("outfit-construction").prompt.lower()

    assert "master reference's open-neck outfit variant is authoritative" in prompt
    assert "upper-body turnaround is authoritative only for pose, scale, body proportions" in prompt
    assert "closed neckline is not garment canon" in prompt
    assert "use the inputs only for visible garment design and approved scale" in prompt
    assert "featureless matte neutral technical mannequin" in prompt
    assert "do not render a human subject, face, hair, skin, or personal features" in prompt
    assert "fitted pearl-white inner layer with a low straight neckline" in prompt
    assert "inner layer remains distinct from the outer jacket" in prompt
    assert "character's final worn appearance remains authoritative only in the master" in prompt
    assert "glossy pearl-white outer technical jacket" in prompt
    assert "leather-or-latex visual finish" in prompt
    assert "center-front metal zipper must remain open to the canonical depth" in prompt
    assert "clean tailored v-shaped neckline" in prompt
    assert "separate black choker" in prompt
    assert "exact visible canonical text `juana ia`" in prompt
    assert "fine necklace with the small approved metallic pendant" in prompt
    assert "rectangular rear choker closure must use a gold finish" in prompt
    assert "organic seam paths, fitted sleeve boundaries, and back construction" in prompt
    assert (
        "do not close the zipper, raise the neckline, or merge the choker into the suit"
        in prompt
    )
    assert "front, left, right, and back garment construction" in prompt
    assert "preserve only exact canonical in-world lettering" in prompt
    assert "preserve the visible identity" not in prompt
    assert "cleavage" not in prompt
    assert "sternum" not in prompt
    assert "chest" not in prompt


def test_material_prompt_limits_each_cell_to_approved_visible_evidence() -> None:
    prompt = TALKING_BUST_PLAN.task("material-reference").prompt.lower()

    assert "top-left skin panel must show evenly lit facial skin and neck" in prompt
    assert "top-middle eyes panel must show both warm amber-brown irises" in prompt
    assert "top-right hair panel must show the near-black hair" in prompt
    assert "subtle warm brown strand variation" in prompt
    assert "bottom-left outfit panel must show two distinct pearl-white layers" in prompt
    assert "fitted inner layer with a low straight neckline" in prompt
    assert "glossy outer technical jacket with a leather-or-latex visual finish" in prompt
    assert "open center-front zipper and clean v-shaped neckline" in prompt
    assert "separate black `juana ia` choker" in prompt
    assert "rectangular rear closure uses a gold finish" in prompt
    assert (
        "bottom-middle accessories panel must show visible exterior references of the approved "
        "gold hoop earrings and fine necklace"
        in prompt
    )
    assert "small metallic pendant" in prompt
    assert "gold rear choker closure" in prompt
    assert "featureless neutral display forms" in prompt
    assert (
        "beyond that approved visible buckle, do not invent earring posts, necklace "
        "clasps, additional closures, backs, or other hidden geometry"
        in prompt
    )
    assert "bottom-right combined palette panel must use unlabeled flat swatches" in prompt
    assert "do not invent hex codes, numeric values, physical shader parameters" in prompt
    assert "do not add unseen materials or accessories" in prompt
    assert "preserve only exact canonical in-world lettering" in prompt


def test_task_dependencies_are_explicit_and_topological() -> None:
    dependencies = {
        task.task_id: task.dependencies for task in TALKING_BUST_PLAN.tasks
    }

    assert dependencies == {
        "face-turnaround": (),
        "facial-mechanics": ("face-turnaround",),
        "upper-body-turnaround": ("face-turnaround",),
        "expressions": ("face-turnaround", "facial-mechanics"),
        "visemes": ("face-turnaround", "facial-mechanics"),
        "hair-construction": ("face-turnaround", "upper-body-turnaround"),
        "outfit-construction": ("upper-body-turnaround",),
        "material-reference": ("hair-construction", "outfit-construction"),
    }


def test_face_panels_map_to_canonical_package_paths_and_crop_boxes() -> None:
    task = TALKING_BUST_PLAN.task("face-turnaround")

    assert [(panel.panel_id, panel.package_path) for panel in task.panels] == [
        ("neutral-front", "references/face/neutral-front.png"),
        ("left-profile", "references/face/left-profile.png"),
        ("right-profile", "references/face/right-profile.png"),
        ("left-three-quarter", "references/face/left-three-quarter.png"),
        ("right-three-quarter", "references/face/right-three-quarter.png"),
    ]
    assert task.crop_box(task.panels[0]) == (0, 0, 512, 512)
    assert task.crop_box(task.panels[-1]) == (512, 512, 1024, 1024)


def test_plan_covers_required_reference_sections_without_path_collisions() -> None:
    paths = [
        panel.package_path
        for task in TALKING_BUST_PLAN.tasks
        for panel in task.panels
    ]

    assert len(paths) == len(set(paths))
    assert {
        "references/body/a-pose-front.png",
        "references/body/a-pose-back.png",
        "references/expressions/happy.png",
        "references/visemes/aa.png",
        "references/visemes/oh.png",
        "references/hair/hairline.png",
        "references/outfit/back.png",
        "references/materials/skin.png",
    }.issubset(paths)


def test_plan_rejects_dependencies_that_are_not_earlier_tasks() -> None:
    payload = TALKING_BUST_PLAN.model_dump(mode="json")
    payload["tasks"][0]["dependencies"] = ["material-reference"]

    with pytest.raises(ValidationError, match="earlier task"):
        AuthoringPlanDefinition.model_validate(payload)


def test_plan_rejects_unknown_task_fields() -> None:
    payload = TALKING_BUST_PLAN.model_dump(mode="json")
    payload["tasks"][0]["dynamic_planner"] = True

    with pytest.raises(ValidationError, match="dynamic_planner"):
        AuthoringPlanDefinition.model_validate(payload)
