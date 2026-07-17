"""Fixed, versioned plan for talking-bust technical reference candidates."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import ConfigDict, Field, model_validator

from vrm_ia_maker.design.contracts import (
    NonEmptyString,
    PackageRelativePath,
    StrictDesignModel,
)


class PanelDefinition(StrictDesignModel):
    """One deterministic grid cell and its canonical package destination."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    panel_id: NonEmptyString
    row: Annotated[int, Field(ge=0)]
    column: Annotated[int, Field(ge=0)]
    package_path: PackageRelativePath


class AuthoringTaskDefinition(StrictDesignModel):
    """One bounded provider request in the fixed authoring workflow."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: NonEmptyString
    order: Annotated[int, Field(ge=0)]
    dependencies: tuple[NonEmptyString, ...] = ()
    include_master: Literal[True] = True
    prompt_id: NonEmptyString
    prompt_version: Literal["1.0", "1.1", "1.2", "1.3", "1.4"] = "1.0"
    prompt: NonEmptyString
    output_format: Literal["png"] = "png"
    width: Annotated[int, Field(gt=0)]
    height: Annotated[int, Field(gt=0)]
    rows: Annotated[int, Field(gt=0)]
    columns: Annotated[int, Field(gt=0)]
    panels: Annotated[tuple[PanelDefinition, ...], Field(min_length=1)]
    max_attempts: Literal[3] = 3

    @model_validator(mode="after")
    def validate_grid(self) -> AuthoringTaskDefinition:
        """Require exact cells and unique, in-bounds panel mappings."""
        if self.width % self.columns or self.height % self.rows:
            raise ValueError("Task dimensions must divide evenly into the declared grid.")
        positions = [(panel.row, panel.column) for panel in self.panels]
        if len(positions) != len(set(positions)):
            raise ValueError("Task panel grid positions must be unique.")
        if any(
            panel.row >= self.rows or panel.column >= self.columns for panel in self.panels
        ):
            raise ValueError("Task panels must fit inside the declared grid.")
        paths = [panel.package_path for panel in self.panels]
        if len(paths) != len(set(paths)):
            raise ValueError("Task panel package paths must be unique.")
        if len(set(self.dependencies)) != len(self.dependencies):
            raise ValueError("Task dependencies must be unique.")
        return self

    def crop_box(self, panel: PanelDefinition) -> tuple[int, int, int, int]:
        """Return the exact Pillow-style crop box for one panel."""
        if panel not in self.panels:
            raise ValueError("Panel does not belong to this task.")
        cell_width = self.width // self.columns
        cell_height = self.height // self.rows
        left = panel.column * cell_width
        top = panel.row * cell_height
        return (left, top, left + cell_width, top + cell_height)


class AuthoringPlanDefinition(StrictDesignModel):
    """Validated immutable DAG for one visual authoring profile."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    plan_id: Literal["talking-bust-v1"] = "talking-bust-v1"
    plan_version: Literal["1.0"] = "1.0"
    tasks: Annotated[tuple[AuthoringTaskDefinition, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def validate_topology(self) -> AuthoringPlanDefinition:
        """Require stable ordering, earlier dependencies, and unique outputs."""
        task_ids = [task.task_id for task in self.tasks]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("Authoring task identifiers must be unique.")
        known: set[str] = set()
        paths: list[str] = []
        for index, task in enumerate(self.tasks):
            if task.order != index:
                raise ValueError("Authoring task order must be contiguous and stable.")
            if any(dependency not in known for dependency in task.dependencies):
                raise ValueError("Every dependency must reference an earlier task.")
            known.add(task.task_id)
            paths.extend(panel.package_path for panel in task.panels)
        if len(paths) != len(set(paths)):
            raise ValueError("Panel package paths must be unique across the plan.")
        return self

    def task(self, task_id: str) -> AuthoringTaskDefinition:
        """Return a task by its stable identifier."""
        for task in self.tasks:
            if task.task_id == task_id:
                return task
        raise KeyError(task_id)


def _panel(
    panel_id: str,
    row: int,
    column: int,
    package_path: str,
) -> PanelDefinition:
    return PanelDefinition(
        panel_id=panel_id,
        row=row,
        column=column,
        package_path=package_path,
    )


def _prompt(
    *,
    rows: int,
    columns: int,
    panel_names: tuple[str, ...],
    task_direction: str,
    preserve_canonical_text: bool = False,
    garment_only: bool = False,
) -> str:
    panel_order = ", ".join(panel_names)
    reference_rules = (
        "Use the inputs only for visible garment design and approved scale and "
        "proportions. Do not transfer the character's personal appearance into this "
        "garment-only construction candidate. "
        if garment_only
        else "Preserve the visible identity, facial structure, skin tone, proportions, "
        "hairstyle, outfit, and material relationships of the master character. "
    )
    presentation_rules = (
        "Use no text as panel labels or explanation, no borders, no gutters, no "
        "watermark, and no added logos. Preserve only exact canonical in-world "
        "lettering explicitly required by the task direction; do not add any other "
        "lettering. "
        if preserve_canonical_text
        else "Use no text, no labels, no borders, no gutters, no logos, and no "
        "watermark. "
    )
    return (
        "Create one bounded technical reference candidate from the supplied approved "
        "character-reference inputs. "
        f"{reference_rules}"
        "Do not present hidden, occluded, inconsistent, or missing "
        "details as measured facts. "
        f"Create a {columns} by {rows} sheet with exact equal cells in row-major order. "
        "Each occupied panel must fill its entire cell, use a flat white background, and "
        "keep consistent scale and neutral technical lighting. "
        f"{presentation_rules}"
        f"Panel order: {panel_order}. {task_direction} "
        "Output exactly one PNG image. The result remains a technical reference candidate "
        "until explicit human approval."
    )


TALKING_BUST_PLAN = AuthoringPlanDefinition(
    tasks=(
        AuthoringTaskDefinition(
            task_id="face-turnaround",
            order=0,
            prompt_id="talking-bust.face-turnaround",
            prompt_version="1.2",
            prompt=_prompt(
                rows=2,
                columns=3,
                panel_names=(
                    "neutral front",
                    "left profile",
                    "right profile",
                    "left three-quarter",
                    "right three-quarter",
                ),
                task_direction=(
                    "The depicted character is an adult. Frame only the head and neck; exclude "
                    "the chest and torso, and use a neutral professional character-model "
                    "presentation. Show the same neutral head and neck at matching scale and "
                    "camera height. Treat left and right as the character's anatomical sides, "
                    "not the viewer's. The left-profile panel must show the shaved temple and "
                    "visible ear. The right-profile panel must show the opposite side: the long "
                    "swept hair must cover the right temple and ear and overlap the facial "
                    "contour. It must not mirror or repeat the shaved side. Preserve the same "
                    "asymmetry in both three-quarter views. Keep eyes open and mouth closed. "
                    "Leave the final unused cell plain white."
                ),
            ),
            width=1536,
            height=1024,
            rows=2,
            columns=3,
            panels=(
                _panel("neutral-front", 0, 0, "references/face/neutral-front.png"),
                _panel("left-profile", 0, 1, "references/face/left-profile.png"),
                _panel("right-profile", 0, 2, "references/face/right-profile.png"),
                _panel(
                    "left-three-quarter",
                    1,
                    0,
                    "references/face/left-three-quarter.png",
                ),
                _panel(
                    "right-three-quarter",
                    1,
                    1,
                    "references/face/right-three-quarter.png",
                ),
            ),
        ),
        AuthoringTaskDefinition(
            task_id="facial-mechanics",
            order=1,
            dependencies=("face-turnaround",),
            prompt_id="talking-bust.facial-mechanics",
            prompt_version="1.1",
            prompt=_prompt(
                rows=2,
                columns=3,
                panel_names=(
                    "eyes open",
                    "both eyes closed",
                    "left-eye blink",
                    "right-eye blink",
                    "jaw open",
                    "neutral closed mouth",
                ),
                task_direction=(
                    "Use the same centered neutral front head. Change only the named eyelid, "
                    "jaw, or mouth mechanism and preserve all unrelated features. Treat left "
                    "and right as the character's anatomical sides. The blink-left panel must "
                    "close only the character's anatomical left eye, which appears on the "
                    "viewer's right beside the shaved temple; keep the other eye open. The "
                    "blink-right panel must close only the character's anatomical right eye, "
                    "which appears on the viewer's left beneath the long hair; keep the other "
                    "eye open. Do not duplicate the same closed eye in both blink panels."
                ),
            ),
            width=1536,
            height=1024,
            rows=2,
            columns=3,
            panels=(
                _panel("eyes-open", 0, 0, "references/face/mechanics/eyes-open.png"),
                _panel("eyes-closed", 0, 1, "references/face/mechanics/eyes-closed.png"),
                _panel("blink-left", 0, 2, "references/face/mechanics/blink-left.png"),
                _panel("blink-right", 1, 0, "references/face/mechanics/blink-right.png"),
                _panel("jaw-open", 1, 1, "references/face/mechanics/jaw-open.png"),
                _panel(
                    "neutral-mouth",
                    1,
                    2,
                    "references/face/mechanics/neutral-mouth.png",
                ),
            ),
        ),
        AuthoringTaskDefinition(
            task_id="upper-body-turnaround",
            order=2,
            dependencies=("face-turnaround",),
            prompt_id="talking-bust.upper-body-turnaround",
            prompt_version="1.2",
            prompt=_prompt(
                rows=2,
                columns=2,
                panel_names=("front", "left", "right", "back"),
                task_direction=(
                    "The depicted character is an adult. Frame from the top of the head through "
                    "the upper torso only and crop above the waist. Use the same fully closed "
                    "high-neck white technical suit with continuous opaque coverage in every "
                    "panel. Keep the chest, waist, and pose neutral and unaccentuated. Show the "
                    "same head, neck, shoulders, arms, and upper torso in a symmetric A-pose. "
                    "Treat left and right as the character's anatomical sides and preserve the "
                    "approved asymmetric hairstyle in every view. The top-right left-side panel "
                    "must expose the shaved left temple and ear. The bottom-left right-side "
                    "panel must show the opposite side, with the long swept hair covering the "
                    "right temple and ear and overlapping the facial contour. It must not mirror "
                    "or repeat the shaved side. Keep camera height, scale, body proportions, and "
                    "garment layers consistent across views."
                ),
            ),
            width=1024,
            height=1024,
            rows=2,
            columns=2,
            panels=(
                _panel("front", 0, 0, "references/body/a-pose-front.png"),
                _panel("left", 0, 1, "references/body/a-pose-left.png"),
                _panel("right", 1, 0, "references/body/a-pose-right.png"),
                _panel("back", 1, 1, "references/body/a-pose-back.png"),
            ),
        ),
        AuthoringTaskDefinition(
            task_id="expressions",
            order=3,
            dependencies=("face-turnaround", "facial-mechanics"),
            prompt_id="talking-bust.expressions",
            prompt=_prompt(
                rows=2,
                columns=3,
                panel_names=("neutral", "happy", "sad", "angry", "surprised", "relaxed"),
                task_direction=(
                    "Use the same centered front head and express the named emotion through "
                    "coherent brows, eyelids, cheeks, and mouth without changing identity."
                ),
            ),
            width=1536,
            height=1024,
            rows=2,
            columns=3,
            panels=tuple(
                _panel(name, index // 3, index % 3, f"references/expressions/{name}.png")
                for index, name in enumerate(
                    ("neutral", "happy", "sad", "angry", "surprised", "relaxed")
                )
            ),
        ),
        AuthoringTaskDefinition(
            task_id="visemes",
            order=4,
            dependencies=("face-turnaround", "facial-mechanics"),
            prompt_id="talking-bust.visemes",
            prompt_version="1.2",
            prompt=_prompt(
                rows=2,
                columns=3,
                panel_names=("neutral", "aa", "ih", "ou", "ee", "oh"),
                task_direction=(
                    "Use the same centered neutral front head. Change only lips, jaw, and visible "
                    "oral opening needed for each VRM viseme; keep eyes and brows neutral. Ih must "
                    "be a natural, relaxed I articulation: use gently spread lips and a narrow "
                    "horizontal opening with the teeth lightly visible, without stretching or "
                    "clenching the lip corners. Keep the jaw and cheeks relaxed; no grimace, "
                    "anger, or smile expression. Ee must use a soft, moderately open "
                    "articulation with lips only slightly spread, a small natural gap, and limited "
                    "upper-tooth "
                    "visibility, not a broad toothy smile. Keep neutral, aa, ou, and oh unchanged."
                ),
            ),
            width=1536,
            height=1024,
            rows=2,
            columns=3,
            panels=tuple(
                _panel(name, index // 3, index % 3, f"references/visemes/{name}.png")
                for index, name in enumerate(("neutral", "aa", "ih", "ou", "ee", "oh"))
            ),
        ),
        AuthoringTaskDefinition(
            task_id="hair-construction",
            order=5,
            dependencies=("face-turnaround", "upper-body-turnaround"),
            prompt_id="talking-bust.hair-construction",
            prompt_version="1.1",
            prompt=_prompt(
                rows=2,
                columns=3,
                panel_names=("front", "left", "right", "back", "top", "hairline"),
                task_direction=(
                    "Treat left and right as the character's anatomical sides. The top-left "
                    "front panel must show the shaved left temple on the viewer's right and the "
                    "long sweep over the character's right side on the viewer's left. The "
                    "top-middle left-side panel must expose the shaved left temple and ear. The "
                    "top-right right-side panel must show the opposite side, with long swept hair "
                    "covering the right temple and ear and overlapping the facial contour. The "
                    "bottom-left back, bottom-middle top, and bottom-right hairline panels must "
                    "preserve the same deep side part, left undercut boundary and right-side "
                    "long-hair root, length, flow, and major clumps. The result must not mirror or "
                    "repeat the shaved side, must not symmetrize the hairstyle, and must not "
                    "invent hidden scalp geometry. Emphasize the silhouette, part, major clumps, "
                    "hairline, and attachment to the head while preserving the approved face and "
                    "upper body."
                ),
            ),
            width=1536,
            height=1024,
            rows=2,
            columns=3,
            panels=tuple(
                _panel(name, index // 3, index % 3, f"references/hair/{name}.png")
                for index, name in enumerate(
                    ("front", "left", "right", "back", "top", "hairline")
                )
            ),
        ),
        AuthoringTaskDefinition(
            task_id="outfit-construction",
            order=6,
            dependencies=("upper-body-turnaround",),
            prompt_id="talking-bust.outfit-construction",
            prompt_version="1.4",
            prompt=_prompt(
                rows=2,
                columns=2,
                panel_names=("front", "left", "right", "back"),
                task_direction=(
                    "The master reference's open-neck outfit variant is authoritative for the "
                    "visible garment design. The approved upper-body turnaround is authoritative "
                    "only for pose, scale, body proportions, and multiview framing; its closed "
                    "neckline is not garment canon. Show front, left, right, and back garment "
                    "construction on the same featureless matte neutral technical mannequin, "
                    "framed from its neck through the garment above the waist. Do not render a "
                    "human subject, face, hair, skin, or personal features. Show a fitted "
                    "pearl-white inner layer with a low straight neckline beneath the open "
                    "jacket. The inner layer remains distinct from the outer jacket in every "
                    "view. The character's final worn appearance remains authoritative only in "
                    "the master reference; this candidate isolates garment construction. "
                    "Preserve the glossy pearl-white outer technical jacket with a "
                    "leather-or-latex visual finish, long sleeves, organic seam paths, fitted "
                    "sleeve boundaries, and back construction. "
                    "The center-front metal zipper must remain open to the canonical depth shown "
                    "in the master and form the same clean tailored V-shaped neckline. "
                    "Keep the separate black choker around the mannequin neck rather than "
                    "attached to the suit, with the exact visible canonical text `JUANA IA` "
                    "across its front. Its rectangular rear choker closure must use a gold "
                    "finish. "
                    "Keep the fine necklace with the small approved metallic pendant below the "
                    "choker. Do not close the zipper, raise the neckline, or merge the choker "
                    "into the suit. Do not merge the inner layer into the outer jacket. Keep both "
                    "garment layers opaque and keep all layers and closures consistent in the "
                    "four cells."
                ),
                preserve_canonical_text=True,
                garment_only=True,
            ),
            width=1024,
            height=1024,
            rows=2,
            columns=2,
            panels=tuple(
                _panel(name, index // 2, index % 2, f"references/outfit/{name}.png")
                for index, name in enumerate(("front", "left", "right", "back"))
            ),
        ),
        AuthoringTaskDefinition(
            task_id="material-reference",
            order=7,
            dependencies=("hair-construction", "outfit-construction"),
            prompt_id="talking-bust.material-reference",
            prompt_version="1.3",
            prompt=_prompt(
                rows=2,
                columns=3,
                panel_names=("skin", "eyes", "hair", "outfit", "accessories", "combined palette"),
                task_direction=(
                    "Create evenly lit close reference crops and flat color swatches for the "
                    "named visible materials. The top-left skin panel must show evenly lit facial "
                    "skin and neck with representative visible tonal variation. The top-middle "
                    "eyes panel must show both warm amber-brown irises under neutral lighting "
                    "without changing gaze or expression. The top-right hair panel must show the "
                    "near-black hair with subtle warm brown strand variation and its approved "
                    "surface texture. The bottom-left outfit panel must show two distinct "
                    "pearl-white layers on a featureless neutral display form: a fitted inner "
                    "layer with a low straight neckline and a glossy outer technical jacket with "
                    "a leather-or-latex visual finish, open center-front zipper and clean "
                    "V-shaped neckline. Include the separate black `JUANA IA` choker; its "
                    "rectangular rear closure uses a gold finish. Show the visible metal zipper "
                    "surface and keep the two garment finishes distinct. The bottom-middle "
                    "accessories panel must show visible exterior references of the approved gold "
                    "hoop earrings and fine necklace with its small metallic pendant, plus the "
                    "gold rear choker closure, on featureless neutral display forms. Beyond that "
                    "approved visible buckle, do not invent earring posts, necklace clasps, "
                    "additional closures, backs, or other hidden geometry. The bottom-right "
                    "combined palette panel must use unlabeled flat swatches sampled only from "
                    "these visible references. Preserve source colors under neutral lighting. Do "
                    "not invent hex codes, numeric values, physical shader parameters, or "
                    "unobserved material behavior. Do not add unseen materials or accessories."
                ),
                preserve_canonical_text=True,
            ),
            width=1536,
            height=1024,
            rows=2,
            columns=3,
            panels=(
                _panel("skin", 0, 0, "references/materials/skin.png"),
                _panel("eyes", 0, 1, "references/materials/eyes.png"),
                _panel("hair", 0, 2, "references/materials/hair.png"),
                _panel("outfit", 1, 0, "references/materials/outfit.png"),
                _panel("accessories", 1, 1, "references/materials/accessories.png"),
                _panel(
                    "combined-palette",
                    1,
                    2,
                    "references/materials/combined-palette.png",
                ),
            ),
        ),
    )
)
