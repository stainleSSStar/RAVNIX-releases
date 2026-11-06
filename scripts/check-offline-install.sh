#!/usr/bin/env bash
# Verify that the installation can run without a network connection.
#
# The installed system is built from the same modules as the live image, plus
# a bootloader configuration. Everything the installation needs has to be in
# the live image already: otherwise the installation depends on the binary
# cache, and a single broken connection to it aborts an installation that has
# already erased the disk. That is exactly what happened during the earlier
# test runs.
#
# The plan of the installed system is compared with what the live image
# carries. Derivations that will be built in the guest are fine, their inputs
# are in the live image. Paths that would have to be fetched are not: they
# need the network.
set -Eeuo pipefail

status=0
for mode in bios uefi; do
  echo "== plan for the $mode installation =="
  plan=$(nix build ".#checks.x86_64-linux.$mode" --dry-run 2>&1) || {
    echo "ERROR: the $mode system could not be evaluated" >&2
    echo "$plan" >&2
    status=1
    continue
  }
  echo "$plan"
  fetched=$(printf '%s\n' "$plan" | awk '
    /will be fetched/ { collect = 1; next }
    collect && /^  \/nix\/store\// { print; next }
    collect { collect = 0 }
  ')
  if [ -n "$fetched" ]; then
    echo "ERROR: the $mode installation would have to fetch these paths:" >&2
    printf '%s\n' "$fetched" >&2
    status=1
  else
    echo "OK: the $mode installation needs nothing from the network."
  fi
done
exit "$status"
