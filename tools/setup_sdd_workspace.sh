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

command -v git >/dev/null 2>&1 || fail "git is required"
command -v sh >/dev/null 2>&1 || fail "POSIX sh is required"

printf 'Initializing pinned SDD kit...\n'
git submodule sync -- .sdd-kit
git submodule update --init --recursive .sdd-kit

[ -f .sdd-kit/VERSION ] || fail ".sdd-kit is not initialized"
actual_version=$(tr -d '\r\n' < .sdd-kit/VERSION)
[ "$actual_version" = "$EXPECTED_KIT_VERSION" ] ||
  fail "expected kathy-sdd-kit version $EXPECTED_KIT_VERSION, got $actual_version"

actual_commit=$(git -C .sdd-kit rev-parse HEAD)
[ "$actual_commit" = "$EXPECTED_KIT_COMMIT" ] ||
  fail "expected kathy-sdd-kit commit $EXPECTED_KIT_COMMIT, got $actual_commit"

printf 'Exposing project-local SDD skills...\n'
sh .sdd-kit/tools/sync-agent-skills.sh --write
sh .sdd-kit/tools/sync-agent-skills.sh --check

printf 'OK: kathy-sdd-kit %s (%s) is ready.\n' \
  "$actual_version" "$actual_commit"
