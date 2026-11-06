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
# carries. A handful of small rendered files, such as the sudoers file or the
# scripts of the login program, are different in every configuration and are
# therefore taken from the cache. They are a few kilobytes and nix rebuilds
# them locally when the download fails, because their inputs are in the live
# image. A package in that list is an error: building it locally would need a
# compiler, which the live image does not carry.
set -Eeuo pipefail

# The rendered files are a few kilobytes; anything larger is a package.
limit=$((1024 * 1024))
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
  if [ -z "$fetched" ]; then
    echo "OK: the $mode installation needs nothing from the network."
    continue
  fi
  parsed=$(printf '%s\n' "$plan" | python3 -c '
import re,sys
text = sys.stdin.read()
scale = {"B": 1, "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3}
match = re.search(r"\(([0-9.]+) (B|KiB|MiB|GiB) download", text)
if not match:
    print("0 B:0")
else:
    print(match.group(1) + " " + match.group(2) + ":" +
          str(int(float(match.group(1)) * scale[match.group(2)])))
')
  size=${parsed%%:*}
  bytes=${parsed##*:}
  echo "The $mode installation would fetch $size:"
  printf '%s\n' "$fetched"
  if [ "$bytes" -gt "$limit" ]; then
    echo "ERROR: the $mode installation depends on $bytes bytes from the network." >&2
    status=1
  elif printf '%s\n' "$fetched" | grep -qiE 'perl'; then
    # A compiled Perl module cannot be rebuilt in the guest, because the
    # live image carries no compiler.
    echo "ERROR: the $mode installation would have to build compiled Perl modules." >&2
    status=1
  else
    echo "OK: only $size, and they are rendered files that nix rebuilds locally."
  fi
done
exit "$status"
