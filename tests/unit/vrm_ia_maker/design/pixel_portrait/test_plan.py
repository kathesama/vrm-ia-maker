"""Tests for the fixed panel-first pixel portrait plan."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from vrm_ia_maker.design.plan import TALKING_BUST_PLAN

_LEGACY_PLAN_SNAPSHOT = TALKING_BUST_PLAN.model_dump(mode="json")

from vrm_ia_maker.design.pixel_portrait.contracts import PanelRuntimeRole  # noqa: E402
from vrm_ia_maker.design.pixel_portrait.plan import (  # noqa: E402
    PIXEL_PORTRAIT_PLAN,
    PanelSourceRole,
    PixelFamilyDefinition,
    PixelPanelDefinition,
    PixelPortraitPlanDefinition,
)

EXPECTED_FAMILY_MEMBERS = {
    "presence-states": (
        "presence-neutral",
        "presence-thinking",
        "presence-explaining",
        "presence-approval",
        "presence-doubt",
        "presence-error",
    ),
    "face-turnaround": (
        "face-neutral-front",
        "face-left-profile",
        "face-right-profile",
        "face-left-three-quarter",
        "face-right-three-quarter",
    ),
    "facial-mechanics": (
        "mechanics-eyes-open",
        "mechanics-eyes-closed",
        "mechanics-blink-left",
        "mechanics-blink-right",
        "mechanics-jaw-open",
        "mechanics-neutral-mouth",
    ),
    "upper-body-turnaround": (
        "body-front",
        "body-left",
        "body-right",
        "body-back",
    ),
    "expressions": (
        "expression-neutral",
        "expression-happy",
        "expression-sad",
        "expression-angry",
        "expression-surprised",
        "expression-relaxed",
    ),
    "visemes": (
        "viseme-neutral",
        "viseme-aa",
        "viseme-ih",
        "viseme-ou",
        "viseme-ee",
        "viseme-oh",
    ),
    "hair-construction": (
        "hair-front",
        "hair-left",
        "hair-right",
        "hair-back",
        "hair-top",
        "hair-hairline",
    ),
    "outfit-construction": (
        "outfit-front",
        "outfit-left",
        "outfit-right",
        "outfit-back",
    ),
    "material-reference": (
        "material-skin",
        "material-hair",
        "material-eyes",
        "material-outfit",
        "material-accessories",
        "material-combined-palette",
    ),
}

EXPECTED_GRIDS = {
    "presence-states": (2, 3),
    "face-turnaround": (2, 3),
    "facial-mechanics": (2, 3),
    "upper-body-turnaround": (2, 2),
    "expressions": (2, 3),
    "visemes": (2, 3),
    "hair-construction": (2, 3),
    "outfit-construction": (2, 2),
    "material-reference": (2, 3),
}

BASE_ANCHOR_REQUIREMENTS = ("pivot", "eye", "mouth", "shoulders")
EXPECTED_FAMILY_ANCHORS = {
    "presence-states": "presence_alignment",
    "face-turnaround": "face_turnaround_alignment",
    "facial-mechanics": "facial_mechanics_alignment",
    "upper-body-turnaround": "upper_body_alignment",
    "expressions": "expression_alignment",
    "visemes": "viseme_alignment",
    "hair-construction": "hair_construction_alignment",
    "outfit-construction": "outfit_construction_alignment",
    "material-reference": "material_reference_alignment",
}


def _payload() -> dict[str, Any]:
    return PIXEL_PORTRAIT_PLAN.model_dump(mode="json")


def test_pixel_plan_has_exact_inventory_family_order_and_grids() -> None:
    assert PIXEL_PORTRAIT_PLAN.plan_id == "juana-talking-bust-v2-pixel"
    assert tuple(family.family_id for family in PIXEL_PORTRAIT_PLAN.families) == tuple(
        EXPECTED_FAMILY_MEMBERS
    )
    assert len(PIXEL_PORTRAIT_PLAN.panels) == 49
    assert len({panel.panel_id for panel in PIXEL_PORTRAIT_PLAN.panels}) == 49
    assert len({panel.package_path for panel in PIXEL_PORTRAIT_PLAN.panels}) == 49

    for position, family in enumerate(PIXEL_PORTRAIT_PLAN.families):
        assert family.family_position == position
        assert family.panel_ids == EXPECTED_FAMILY_MEMBERS[family.family_id]
        assert family.ordered_panel_ids == family.panel_ids
        assert (family.rows, family.columns) == EXPECTED_GRIDS[family.family_id]
        assert (family.sheet_rows, family.sheet_columns) == (family.rows, family.columns)
        assert family.sheet_package_path == (
            f"references/master/approved-sheets/{family.family_id}.png"
        )


def test_panels_follow_exact_family_membership_order_and_dimensions() -> None:
    expected_order = tuple(
        panel_id for panel_ids in EXPECTED_FAMILY_MEMBERS.values() for panel_id in panel_ids
    )
    assert tuple(panel.panel_id for panel in PIXEL_PORTRAIT_PLAN.panels) == expected_order

    for family in PIXEL_PORTRAIT_PLAN.families:
        panels = tuple(
            panel for panel in PIXEL_PORTRAIT_PLAN.panels if panel.family_id == family.family_id
        )
        assert tuple(panel.panel_id for panel in panels) == family.panel_ids
        assert tuple(panel.family_position for panel in panels) == tuple(range(len(panels)))
        assert len(panels) <= family.rows * family.columns

    for panel in PIXEL_PORTRAIT_PLAN.panels:
        assert (panel.request_width, panel.request_height) == (1024, 1024)
        assert (panel.logical_width, panel.logical_height) == (256, 256)
        assert (panel.file_width, panel.file_height) == (512, 512)
        assert panel.prompt_id == f"pixel-panel.{panel.panel_id}"
        assert panel.prompt_version == "pixel-panel-v1"


def test_every_family_and_panel_has_exact_canonical_anchor_requirements() -> None:
    for family in PIXEL_PORTRAIT_PLAN.families:
        expected = (*BASE_ANCHOR_REQUIREMENTS, EXPECTED_FAMILY_ANCHORS[family.family_id])
        assert family.anchor_contract.family_id == family.family_id
        assert family.anchor_contract.required_anchors == expected
        for panel_id in family.panel_ids:
            panel = PIXEL_PORTRAIT_PLAN.panel(panel_id)
            assert panel.anchor_contract == family.anchor_contract


def test_panel_anchor_contract_is_required_strict_and_immutable() -> None:
    panel = PIXEL_PORTRAIT_PLAN.panel("presence-neutral")
    payload = panel.model_dump(mode="json")
    payload.pop("anchor_contract")
    with pytest.raises(ValidationError, match="anchor_contract"):
        PixelPanelDefinition.model_validate(payload)

    valid_contract = panel.anchor_contract.model_dump(mode="json")
    for mutation, message in (
        (
            lambda value: value["required_anchors"].remove("mouth"),
            "canonical anchor requirements",
        ),
        (
            lambda value: value["required_anchors"].append("face_turnaround_alignment"),
            "canonical anchor requirements",
        ),
        (
            lambda value: value["required_anchors"].append("pivot"),
            "must not contain duplicates",
        ),
        (
            lambda value: value.update(dynamic_anchor="forbidden"),
            "dynamic_anchor",
        ),
    ):
        invalid = panel.model_dump(mode="json")
        invalid_contract = {
            key: list(item) if isinstance(item, list) else item
            for key, item in valid_contract.items()
        }
        mutation(invalid_contract)
        invalid["anchor_contract"] = invalid_contract
        with pytest.raises(ValidationError, match=message):
            PixelPanelDefinition.model_validate(invalid)

    with pytest.raises(ValidationError) as frozen_error:
        panel.anchor_contract.required_anchors = ()
    assert frozen_error.value.errors()[0]["loc"] == ("required_anchors",)
    assert frozen_error.value.errors()[0]["type"] == "frozen_instance"


def test_panel_rejects_another_family_anchor_contract() -> None:
    payload = PIXEL_PORTRAIT_PLAN.panel("presence-neutral").model_dump(mode="json")
    payload["anchor_contract"] = PIXEL_PORTRAIT_PLAN.family("visemes").anchor_contract.model_dump(
        mode="json"
    )

    with pytest.raises(ValidationError, match="match the panel family"):
        PixelPanelDefinition.model_validate(payload)


def test_base_prompt_single_sources_required_pixel_identity_rules() -> None:
    prompt = PIXEL_PORTRAIT_PLAN.base_prompt.lower()
    required_phrases = (
        "younger base-set juana identity",
        "viewer-left shaved side",
        "viewer-right long hair",
        "fine pixel art",
        "one 256x256 logical grid emitted as 512x512 nearest-neighbor-safe artwork",
        "transparent or solid neutral background",
        "no text, labels, or extra panels",
        "preserve only the named view or articulation",
        "do not invent hidden geometry or measurements",
    )
    assert all(phrase in prompt for phrase in required_phrases)
    assert len({panel.prompt_instruction for panel in PIXEL_PORTRAIT_PLAN.panels}) == 49
    assert all(panel.prompt_instruction for panel in PIXEL_PORTRAIT_PLAN.panels)


def test_presence_panels_have_exact_paths_sources_and_dependencies() -> None:
    for member in ("neutral", "thinking", "explaining", "approval", "doubt", "error"):
        panel = PIXEL_PORTRAIT_PLAN.panel(f"presence-{member}")
        assert panel.package_path == f"references/presence-states/{member}.png"
        assert panel.base_source_role == member
        if member == "neutral":
            assert panel.technical_source_path == "references/face/neutral-front.png"
            assert panel.source_roles == (
                PanelSourceRole.BASE_CHARACTER_SHEET,
                PanelSourceRole.BASE_STATE,
                PanelSourceRole.TECHNICAL_REFERENCE,
            )
            assert panel.dependencies == ()
        else:
            assert panel.technical_source_path is None
            assert panel.source_roles == (
                PanelSourceRole.BASE_CHARACTER_SHEET,
                PanelSourceRole.BASE_STATE,
                PanelSourceRole.APPROVED_NEUTRAL,
            )
            assert panel.dependencies == ("presence-neutral",)


def test_technical_panels_have_exact_paths_sources_and_dependencies() -> None:
    expected_paths: dict[str, str] = {}
    families = (
        ("face", "references/face", EXPECTED_FAMILY_MEMBERS["face-turnaround"]),
        (
            "mechanics",
            "references/face/mechanics",
            EXPECTED_FAMILY_MEMBERS["facial-mechanics"],
        ),
        ("expression", "references/expressions", EXPECTED_FAMILY_MEMBERS["expressions"]),
        ("viseme", "references/visemes", EXPECTED_FAMILY_MEMBERS["visemes"]),
        ("hair", "references/hair", EXPECTED_FAMILY_MEMBERS["hair-construction"]),
        ("outfit", "references/outfit", EXPECTED_FAMILY_MEMBERS["outfit-construction"]),
        (
            "material",
            "references/materials",
            EXPECTED_FAMILY_MEMBERS["material-reference"],
        ),
    )
    for prefix, directory, panel_ids in families:
        for panel_id in panel_ids:
            member = panel_id.removeprefix(f"{prefix}-")
            expected_paths[panel_id] = f"{directory}/{member}.png"
    for panel_id in EXPECTED_FAMILY_MEMBERS["upper-body-turnaround"]:
        member = panel_id.removeprefix("body-")
        expected_paths[panel_id] = f"references/body/a-pose-{member}.png"

    assert len(expected_paths) == 43
    for panel_id, expected_path in expected_paths.items():
        panel = PIXEL_PORTRAIT_PLAN.panel(panel_id)
        assert panel.package_path == expected_path
        assert panel.technical_source_path == expected_path
        assert panel.base_source_role is None
        assert panel.source_roles == (
            PanelSourceRole.BASE_CHARACTER_SHEET,
            PanelSourceRole.APPROVED_NEUTRAL,
            PanelSourceRole.TECHNICAL_REFERENCE,
        )
        assert panel.dependencies == ("presence-neutral",)


def test_runtime_roles_are_exact() -> None:
    panels_by_role = {
        role: {panel.panel_id for panel in PIXEL_PORTRAIT_PLAN.panels if panel.runtime_role is role}
        for role in PanelRuntimeRole
    }
    assert panels_by_role[PanelRuntimeRole.STATE] == set(EXPECTED_FAMILY_MEMBERS["presence-states"])
    assert panels_by_role[PanelRuntimeRole.EYE_PATCH] == {
        "mechanics-eyes-open",
        "mechanics-eyes-closed",
        "mechanics-blink-left",
        "mechanics-blink-right",
    }
    assert panels_by_role[PanelRuntimeRole.MOUTH_PATCH] == set(EXPECTED_FAMILY_MEMBERS["visemes"])
    runtime_panel_ids = set().union(
        panels_by_role[PanelRuntimeRole.STATE],
        panels_by_role[PanelRuntimeRole.EYE_PATCH],
        panels_by_role[PanelRuntimeRole.MOUTH_PATCH],
    )
    assert (
        panels_by_role[PanelRuntimeRole.AUTHORING_ONLY]
        == {panel.panel_id for panel in PIXEL_PORTRAIT_PLAN.panels} - runtime_panel_ids
    )


def test_plan_lookups_return_members_and_raise_stable_errors() -> None:
    assert PIXEL_PORTRAIT_PLAN.panel("presence-neutral").panel_id == "presence-neutral"
    assert PIXEL_PORTRAIT_PLAN.family("visemes").family_id == "visemes"

    with pytest.raises(KeyError) as panel_error:
        PIXEL_PORTRAIT_PLAN.panel("missing-panel")
    assert panel_error.value.args == ("Unknown pixel portrait panel: missing-panel",)

    with pytest.raises(KeyError) as family_error:
        PIXEL_PORTRAIT_PLAN.family("missing-family")
    assert family_error.value.args == ("Unknown pixel portrait family: missing-family",)


def test_panel_definition_rejects_unsafe_paths_self_dependency_and_bad_size() -> None:
    panel_payload = PIXEL_PORTRAIT_PLAN.panels[0].model_dump(mode="json")
    for field in ("package_path", "technical_source_path"):
        unsafe = dict(panel_payload)
        unsafe[field] = "../outside.png"
        with pytest.raises(ValidationError, match="package-relative path"):
            PixelPanelDefinition.model_validate(unsafe)

    self_dependent = dict(panel_payload)
    self_dependent["dependencies"] = [panel_payload["panel_id"]]
    with pytest.raises(ValidationError, match="cannot depend on itself"):
        PixelPanelDefinition.model_validate(self_dependent)

    wrong_size = dict(panel_payload)
    wrong_size["logical_width"] = 512
    with pytest.raises(ValidationError) as size_error:
        PixelPanelDefinition.model_validate(wrong_size)
    assert size_error.value.errors()[0]["loc"] == ("logical_width",)
    assert size_error.value.errors()[0]["type"] == "literal_error"


def test_direct_family_validation_rejects_noncanonical_leaf_metadata() -> None:
    canonical = PIXEL_PORTRAIT_PLAN.family("presence-states").model_dump(mode="json")
    mutations = (
        ("rows", 99),
        ("columns", 99),
        ("family_position", 99),
        ("panel_ids", list(reversed(canonical["panel_ids"]))),
    )
    for field, value in mutations:
        invalid = dict(canonical)
        invalid[field] = value
        with pytest.raises(ValidationError, match="canonical family metadata"):
            PixelFamilyDefinition.model_validate(invalid)

    unknown = dict(canonical)
    unknown["family_id"] = "presence-custom"
    unknown["anchor_contract"] = dict(canonical["anchor_contract"])
    unknown["anchor_contract"]["family_id"] = "presence-custom"
    with pytest.raises(ValidationError):
        PixelFamilyDefinition.model_validate(unknown)


def test_direct_panel_validation_rejects_noncanonical_leaf_metadata() -> None:
    canonical = PIXEL_PORTRAIT_PLAN.panel("presence-thinking").model_dump(mode="json")
    unknown = dict(canonical)
    unknown["panel_id"] = "presence-custom"
    with pytest.raises(ValidationError):
        PixelPanelDefinition.model_validate(unknown)

    mutations = (
        ("family_position", 99),
        ("package_path", "references/presence-states/custom.png"),
        ("base_source_role", "custom"),
        ("source_roles", list(reversed(canonical["source_roles"]))),
        ("dependencies", ["presence-neutral", "face-neutral-front"]),
        ("runtime_role", "authoring_only"),
        ("prompt_instruction", "Render an arbitrary panel."),
        ("prompt_id", "pixel-panel.custom"),
    )
    for field, value in mutations:
        invalid = dict(canonical)
        invalid[field] = value
        with pytest.raises(ValidationError, match="canonical panel metadata"):
            PixelPanelDefinition.model_validate(invalid)


def test_direct_panel_validation_rejects_noncanonical_source_path_and_roles() -> None:
    payload = PIXEL_PORTRAIT_PLAN.panel("presence-thinking").model_dump(mode="json")
    payload["technical_source_path"] = "references/face/neutral-front.png"
    payload["source_roles"] = [
        "base_character_sheet",
        "base_state",
        "approved_neutral",
        "technical_reference",
    ]

    with pytest.raises(ValidationError, match="canonical panel metadata"):
        PixelPanelDefinition.model_validate(payload)


def test_family_definition_rejects_insufficient_grid_capacity() -> None:
    family_payload = PIXEL_PORTRAIT_PLAN.families[0].model_dump(mode="json")
    family_payload.update(rows=1, columns=1)
    with pytest.raises(ValidationError, match="grid capacity"):
        PixelFamilyDefinition.model_validate(family_payload)


def test_plan_rejects_duplicate_missing_and_non_topological_panels() -> None:
    duplicate_id = _payload()
    duplicate_id["panels"][2] = dict(duplicate_id["panels"][1])
    with pytest.raises(ValidationError, match="Panel identifiers must be unique"):
        PixelPortraitPlanDefinition.model_validate(duplicate_id)

    duplicate_path = _payload()
    duplicate_path["panels"][1]["package_path"] = duplicate_path["panels"][0]["package_path"]
    with pytest.raises(ValidationError, match="canonical panel metadata"):
        PixelPortraitPlanDefinition.model_validate(duplicate_path)

    missing_panel = _payload()
    missing_panel["panels"].pop()
    with pytest.raises(ValidationError, match="exactly one panel definition"):
        PixelPortraitPlanDefinition.model_validate(missing_panel)

    invalid_topology = _payload()
    invalid_topology["panels"][0]["dependencies"] = ["material-skin"]
    with pytest.raises(ValidationError, match="canonical panel metadata"):
        PixelPortraitPlanDefinition.model_validate(invalid_topology)

    missing_family = _payload()
    removed_family = missing_family["families"].pop()
    removed_panel_ids = set(removed_family["panel_ids"])
    missing_family["panels"] = [
        panel for panel in missing_family["panels"] if panel["panel_id"] not in removed_panel_ids
    ]
    with pytest.raises(ValidationError, match="fixed nine-family inventory"):
        PixelPortraitPlanDefinition.model_validate(missing_family)


@pytest.mark.parametrize(
    ("model", "payload", "field"),
    (
        (PixelPortraitPlanDefinition, _payload, "dynamic_discovery"),
        (
            PixelPanelDefinition,
            lambda: PIXEL_PORTRAIT_PLAN.panels[0].model_dump(mode="json"),
            "provider_hint",
        ),
        (
            PixelFamilyDefinition,
            lambda: PIXEL_PORTRAIT_PLAN.families[0].model_dump(mode="json"),
            "filesystem_glob",
        ),
    ),
)
def test_plan_models_reject_unknown_fields(
    model: type[PixelPortraitPlanDefinition]
    | type[PixelPanelDefinition]
    | type[PixelFamilyDefinition],
    payload: Any,
    field: str,
) -> None:
    invalid = payload()
    invalid[field] = "forbidden"
    with pytest.raises(ValidationError, match=field):
        model.model_validate(invalid)


def test_importing_pixel_plan_does_not_mutate_legacy_plan() -> None:
    assert TALKING_BUST_PLAN.model_dump(mode="json") == _LEGACY_PLAN_SNAPSHOT
    assert TALKING_BUST_PLAN.plan_id == "talking-bust-v1"
    assert tuple(task.task_id for task in TALKING_BUST_PLAN.tasks) == (
        "face-turnaround",
        "facial-mechanics",
        "upper-body-turnaround",
        "expressions",
        "visemes",
        "hair-construction",
        "outfit-construction",
        "material-reference",
    )
