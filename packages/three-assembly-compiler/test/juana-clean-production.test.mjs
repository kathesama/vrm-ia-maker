import assert from "node:assert/strict";
import test from "node:test";

import { validateJuanaInspection } from "../../../tools/juana_bust/inspect_glb.mjs";

const REQUIRED_BONES = [
  "root",
  "spine05",
  "spine03",
  "spine01",
  "neck03",
  "head",
  "eyeL",
  "eyeR",
  "jaw",
  "clavicleL",
  "upperarm01L",
  "lowerarm01L",
  "wristL",
  "clavicleR",
  "upperarm01R",
  "lowerarm01R",
  "wristR",
];

const ADAPTER = {
  bones: {
    hips: "root",
    spine: "spine05",
    chest: "spine03",
    upperChest: "spine01",
    neck: "neck03",
    head: "head",
    leftEye: "eye.L",
    rightEye: "eye.R",
    jaw: "jaw",
    leftShoulder: "clavicle.L",
    leftUpperArm: "upperarm01.L",
    leftLowerArm: "lowerarm01.L",
    leftHand: "wrist.L",
    rightShoulder: "clavicle.R",
    rightUpperArm: "upperarm01.R",
    rightLowerArm: "lowerarm01.R",
    rightHand: "wrist.R",
  },
  expression_map: {
    blink: [{ shape_key: "blink", weight: 1 }],
  },
};

function cleanInspection() {
  return {
    objectNames: [
      "Juana_Production_Rig",
      "Juana_Production_Body",
      "Juana_Production_Head",
      "Juana_Production_Eye_L",
      "Juana_Production_Eye_R",
      "Juana_Production_Eyebrows",
      "Juana_Production_Eyelashes",
      "Juana_Production_Hair_01",
      "Juana_Production_Outfit_01",
      ...REQUIRED_BONES,
    ],
    boneNames: [...REQUIRED_BONES],
    morphTargets: [],
    materialNames: [],
    skinnedMeshes: {
      Juana_Production_Body: [...REQUIRED_BONES],
      Juana_Production_Head: [...REQUIRED_BONES],
      Juana_Production_Hair_01: [...REQUIRED_BONES],
      Juana_Production_Outfit_01: [...REQUIRED_BONES],
    },
  };
}

test("accepts one clean production character while expressions remain deferred", () => {
  assert.doesNotThrow(() => validateJuanaInspection(cleanInspection(), ADAPTER));
});

test("rejects donor or procedural spike geometry after Three.js loading", () => {
  const inspection = cleanInspection();
  inspection.objectNames.push("DonorVRM_Body");

  assert.throws(
    () => validateJuanaInspection(inspection, ADAPTER),
    /Donor or procedural spike geometry survived/,
  );
});

test("requires both production body and head to be skinned", () => {
  const inspection = cleanInspection();
  delete inspection.skinnedMeshes.Juana_Production_Head;

  assert.throws(
    () => validateJuanaInspection(inspection, ADAPTER),
    /Juana_Production_Head must load as a skinned mesh/,
  );
});
