import path from "node:path";

const SUPPORTED_MANIFEST_VERSION = "1.0";

function requireMembers(actualValues, requiredValues, label) {
  const actual = new Set(actualValues ?? []);
  const missing = (requiredValues ?? []).filter((value) => !actual.has(value));
  if (missing.length > 0) {
    throw new Error(`${label} is missing: ${missing.join(", ")}.`);
  }
}

function resolveBoolean(value, defaultValue, label) {
  const resolved = value === undefined ? defaultValue : value;
  if (typeof resolved !== "boolean") {
    throw new Error(`${label} must be a boolean.`);
  }
  return resolved;
}

function resolvedSkinBones(skinnedMeshes, objectName) {
  if (skinnedMeshes instanceof Map) {
    return skinnedMeshes.get(objectName);
  }
  return skinnedMeshes?.[objectName];
}

function verifyIntegrity(asset, inspection) {
  if (inspection.sha256 !== asset.sha256) {
    throw new Error(
      `SHA-256 mismatch for ${asset.asset_id}: expected ${asset.sha256}, ` +
        `got ${inspection.sha256}.`,
    );
  }
  if (inspection.byteLength !== asset.byte_length) {
    throw new Error(
      `Byte-length mismatch for ${asset.asset_id}: expected ${asset.byte_length}, ` +
        `got ${inspection.byteLength}.`,
    );
  }
}

function validateManifestRelationships(assetPack, assembly, baseAdapter) {
  const assetPackVersion = assetPack.schema_version ?? SUPPORTED_MANIFEST_VERSION;
  const assemblyVersion = assembly.schema_version ?? SUPPORTED_MANIFEST_VERSION;
  const adapterVersion = baseAdapter.schema_version ?? SUPPORTED_MANIFEST_VERSION;
  if (
    assetPackVersion !== SUPPORTED_MANIFEST_VERSION ||
    assemblyVersion !== SUPPORTED_MANIFEST_VERSION ||
    adapterVersion !== SUPPORTED_MANIFEST_VERSION
  ) {
    throw new Error("Asset pack, assembly, and base adapter must use schema_version 1.0.");
  }
  if (assembly.asset_pack_id !== assetPack.pack_id) {
    throw new Error(
      `Assembly references asset pack ${assembly.asset_pack_id}, expected ${assetPack.pack_id}.`,
    );
  }
  if (baseAdapter.base_asset_id !== assetPack.base_asset.asset_id) {
    throw new Error(
      `Base adapter references asset ${baseAdapter.base_asset_id}, ` +
        `expected ${assetPack.base_asset.asset_id}.`,
    );
  }
}

function resolveSelections(assetPack, assembly) {
  const componentById = new Map(
    assetPack.components.map((component) => [component.asset_id, component]),
  );
  const selected = [];
  const disabled = [];

  for (const [slot, selection] of Object.entries(assembly.selections).sort(([left], [right]) =>
    left.localeCompare(right),
  )) {
    const component = componentById.get(selection.asset_id);
    if (!component) {
      throw new Error(`Assembly selects unknown asset ${selection.asset_id} for slot ${slot}.`);
    }
    if (component.slot !== slot) {
      throw new Error(
        `Assembly selects ${selection.asset_id} for ${slot}, ` +
          `but the asset belongs to ${component.slot}.`,
      );
    }
    const enabled = resolveBoolean(selection.enabled, true, `Selection ${slot} enabled`);
    (enabled ? selected : disabled).push(component);
  }

  const selectedIds = new Set(selected.map((component) => component.asset_id));
  for (const component of assetPack.components) {
    const required = resolveBoolean(
      component.required,
      false,
      `Component ${component.asset_id} required`,
    );
    if (required && !selectedIds.has(component.asset_id)) {
      throw new Error(`Required component ${component.asset_id} must be selected and enabled.`);
    }
  }

  return { selected, disabled };
}

export function resolveAssetPath(assetPackPath, assetPath) {
  const root = path.dirname(path.resolve(assetPackPath));
  if (path.isAbsolute(assetPath)) {
    return path.resolve(assetPath);
  }

  const resolved = path.resolve(root, assetPath);
  const relative = path.relative(root, resolved);
  if (relative === ".." || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative)) {
    throw new Error(`Asset path escapes the asset-pack directory: ${assetPath}.`);
  }
  return resolved;
}

function validateBaseIntegration(baseAsset, baseAdapter, inspection) {
  requireMembers(inspection.objectNames, baseAsset.required_objects, "Base asset objects");
  requireMembers(inspection.boneNames, baseAsset.required_bones, "Base asset bones");
  requireMembers(
    inspection.morphTargets,
    baseAsset.required_expressions,
    "Base asset expressions",
  );
  requireMembers(
    inspection.boneNames,
    Object.values(baseAdapter.bones),
    "Adapter-mapped base bones",
  );
  const adapterShapeKeys = Object.values(baseAdapter.expression_map).flatMap((bindings) =>
    bindings.map((binding) => binding.shape_key),
  );
  requireMembers(inspection.morphTargets, adapterShapeKeys, "Adapter-mapped shape keys");
}

function validateComponentIntegration(component, inspection, baseBoneNames) {
  requireMembers(
    inspection.objectNames,
    [component.object_name],
    `Component ${component.asset_id} objects`,
  );
  requireMembers(
    inspection.materialNames,
    component.material_names,
    `Component ${component.asset_id} materials`,
  );

  if (component.kind === "rigid_attachment") {
    if (!baseBoneNames.has(component.attachment_bone)) {
      throw new Error(
        `Rigid component ${component.asset_id} references unknown attachment bone ` +
          `${component.attachment_bone}.`,
      );
    }
    return;
  }
  if (component.kind !== "skinned_mesh") {
    throw new Error(`Unsupported component kind: ${component.kind}.`);
  }

  const skinBones = resolvedSkinBones(inspection.skinnedMeshes, component.object_name);
  if (!skinBones) {
    throw new Error(`Component ${component.asset_id} does not expose a skinned mesh.`);
  }
  requireMembers(
    skinBones,
    component.required_bones,
    `Component ${component.asset_id} skin bones`,
  );
  const unknownBones = skinBones.filter((boneName) => !baseBoneNames.has(boneName));
  if (unknownBones.length > 0) {
    throw new Error(
      `Component ${component.asset_id} uses bones absent from the base: ` +
        `${unknownBones.join(", ")}.`,
    );
  }
}

function createResolvedComponent(component, assetPath) {
  return {
    asset_id: component.asset_id,
    path: assetPath,
    object_name: component.object_name,
    sha256: component.sha256,
    slot: component.slot,
    kind: component.kind,
    attachment_bone: component.attachment_bone ?? null,
    required_bones: component.required_bones ?? [],
    material_names: component.material_names ?? [],
  };
}

export async function compileAssembly({
  assetPackPath,
  assetPack,
  assembly,
  baseAdapter,
  inspectAsset,
}) {
  // sdd-simplification: Node trusts prevalidated manifests - upgrade path: the
  // production vrm-maker use case validates all inputs with Pydantic before invocation.
  validateManifestRelationships(assetPack, assembly, baseAdapter);
  const { selected, disabled } = resolveSelections(assetPack, assembly);
  const selectedIds = new Set(selected.map((component) => component.asset_id));
  const allAssets = [assetPack.base_asset, ...assetPack.components];
  const assetPackRoot = path.dirname(path.resolve(assetPackPath));
  const inspections = new Map();
  const integrityReports = [];

  for (const asset of allAssets) {
    const assetPath = resolveAssetPath(assetPackPath, asset.path);
    const structural =
      asset.asset_id === assetPack.base_asset.asset_id || selectedIds.has(asset.asset_id);
    const allowedRoot = path.isAbsolute(asset.path) ? null : assetPackRoot;
    const inspection = await inspectAsset(assetPath, { structural, allowedRoot });
    verifyIntegrity(asset, inspection);
    inspections.set(asset.asset_id, { assetPath, inspection });
    integrityReports.push({
      asset_id: asset.asset_id,
      path: assetPath,
      byte_length: inspection.byteLength,
      sha256: inspection.sha256,
    });
  }

  const baseRecord = inspections.get(assetPack.base_asset.asset_id);
  validateBaseIntegration(assetPack.base_asset, baseAdapter, baseRecord.inspection);
  const baseBoneNames = new Set(baseRecord.inspection.boneNames);
  const availableMaterials = new Set(baseRecord.inspection.materialNames);
  const resolvedComponents = selected.map((component) => {
    const record = inspections.get(component.asset_id);
    validateComponentIntegration(component, record.inspection, baseBoneNames);
    for (const materialName of record.inspection.materialNames) {
      availableMaterials.add(materialName);
    }
    return createResolvedComponent(component, record.assetPath);
  });

  const materialOverrides = assembly.material_overrides ?? {};
  const unknownMaterials = Object.keys(materialOverrides).filter(
    (materialName) => !availableMaterials.has(materialName),
  );
  if (unknownMaterials.length > 0) {
    throw new Error(
      `Material overrides reference unknown materials: ${unknownMaterials.join(", ")}.`,
    );
  }

  const disabledComponents = disabled.map((component) => ({
    asset_id: component.asset_id,
    slot: component.slot,
    object_name: component.object_name,
  }));
  const compiledSpec = {
    schema_version: "1.1",
    character_id: assembly.character_id,
    display_name: assembly.display_name,
    asset_pack_id: assetPack.pack_id,
    base_adapter_id: baseAdapter.adapter_id,
    base_adapter_version: baseAdapter.adapter_version,
    provenance: assetPack.provenance,
    base_asset: {
      asset_id: assetPack.base_asset.asset_id,
      path: baseRecord.assetPath,
      object_name: assetPack.base_asset.object_name,
      sha256: assetPack.base_asset.sha256,
    },
    components: resolvedComponents,
    disabled_components: disabledComponents,
    material_overrides: materialOverrides,
    vrm_spec: {
      spec_version: "1.0",
      avatar_id: assembly.character_id,
      display_name: assembly.display_name,
      base_asset_id: assetPack.base_asset.asset_id,
      bones: baseAdapter.bones,
      expression_map: baseAdapter.expression_map,
      look_at: baseAdapter.look_at,
      metadata: assembly.metadata,
    },
  };

  return {
    compiledSpec,
    inspection: {
      compiler: "three-assembly-compiler",
      character_id: assembly.character_id,
      asset_pack_id: assetPack.pack_id,
      base_adapter_id: baseAdapter.adapter_id,
      base_adapter_version: baseAdapter.adapter_version,
      asset_integrity: integrityReports,
      selected_components: resolvedComponents,
      disabled_components: disabledComponents,
    },
  };
}
