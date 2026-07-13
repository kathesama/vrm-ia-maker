#!/usr/bin/env sh
set -eu

EXPECTED_KIT_VERSION="0.6.0"
EXPECTED_KIT_COMMIT="2164c5e83a70d88fbb7933a433193a019d8e4cf2"

fail() {
  printf 'FAIL: %s\n' "$1" >&2
  exit 1
}

script_dir=$(CDPATH= cd "$(dirname "$0")" && pwd)
repo_root=$(dirname "$script_dir")
cd "$repo_root"

[ -f .sdd-kit/VERSION ] ||
  fail ".sdd-kit is not initialized; run sh tools/setup_sdd_workspace.sh"

actual_version=$(tr -d '\r\n' < .sdd-kit/VERSION)
[ "$actual_version" = "$EXPECTED_KIT_VERSION" ] ||
  fail "expected kathy-sdd-kit version $EXPECTED_KIT_VERSION, got $actual_version"

actual_commit=$(git -C .sdd-kit rev-parse HEAD)
[ "$actual_commit" = "$EXPECTED_KIT_COMMIT" ] ||
  fail "expected kathy-sdd-kit commit $EXPECTED_KIT_COMMIT, got $actual_commit"

sh .sdd-kit/tools/sync-agent-skills.sh --check
(
  cd .sdd-kit
  sh tools/validate-engineering-rules.sh
)

printf 'OK: SDD workspace is synchronized and the pinned kit validates.\n'
