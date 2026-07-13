#!/usr/bin/env sh
set -eu

EXPECTED_KIT_VERSION="0.6.0"
EXPECTED_KIT_COMMIT="2164c5e83a70d88fbb7933a433193a019d8e4cf2"

fail() {
  printf 'FAIL: %s\n' "$1" >&2
  exit 1
}

require_file() {
  [ -f "$1" ] || fail "missing required SDD kit file: $1"
}

require_text() {
  grep -Fq -- "$2" "$1" || fail "$1 must contain: $2"
}

script_dir=$(CDPATH= cd "$(dirname "$0")" && pwd)
repo_root=$(dirname "$script_dir")
cd "$repo_root"

require_file .sdd-kit/VERSION
actual_version=$(tr -d '\r\n' < .sdd-kit/VERSION)
[ "$actual_version" = "$EXPECTED_KIT_VERSION" ] ||
  fail "expected kathy-sdd-kit version $EXPECTED_KIT_VERSION, got $actual_version"

actual_commit=$(git -C .sdd-kit rev-parse HEAD)
[ "$actual_commit" = "$EXPECTED_KIT_COMMIT" ] ||
  fail "expected kathy-sdd-kit commit $EXPECTED_KIT_COMMIT, got $actual_commit"

# A consuming repository validates the mounted public contract and its local
# exposures. The kit's validate-engineering-rules.sh is an upstream self-test
# for kathy-sdd-kit itself and is intentionally not re-run from the consumer.
for required_path in \
  .sdd-kit/AGENTS.md \
  .sdd-kit/CLAUDE.md \
  .sdd-kit/CODEX.md \
  .sdd-kit/ai-specs/specs/agent-behavior-standards.mdc \
  .sdd-kit/ai-specs/specs/design-system-standards.mdc \
  .sdd-kit/ai-specs/specs/implementation-spec-template.md \
  .sdd-kit/ai-specs/rules/engineering/README.md \
  .sdd-kit/tools/sync-agent-skills.sh \
  .sdd-kit/tools/validate-impl-spec.sh \
  .sdd-kit/tools/validate-changelog.sh \
  .sdd-kit/tools/validate-pr-content.sh
 do
  require_file "$required_path"
 done

require_file AGENTS.md
require_file CLAUDE.md
require_text AGENTS.md ".sdd-kit/CODEX.md"
require_text CLAUDE.md "@.sdd-kit/CLAUDE.md"
require_text AGENTS.md "GH-{number}"

sh .sdd-kit/tools/sync-agent-skills.sh --check

printf 'OK: SDD workspace is synchronized with kathy-sdd-kit %s (%s).\n' \
  "$actual_version" "$actual_commit"
