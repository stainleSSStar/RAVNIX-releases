#!/usr/bin/env bash
# Print the version, Nix hash and URL for the newest Brave Origin release.
#
# Brave Origin is the standalone, feature-stripped Brave build that is free on
# Linux. It is published as a .deb in Brave's apt pool; nixpkgs does not
# package it, so RAVNIX repackages it in pkgs/brave-origin.nix.
#
# Usage: bash scripts/update-brave-origin.sh
set -euo pipefail

pool=https://brave-browser-apt-release.s3.brave.com
index="$pool/dists/stable/main/binary-amd64/Packages"

version=$(curl -fsSL "$index" | awk '
  /^Package: brave-origin$/ { found = 1; next }
  found && /^Version: / { print $2; exit }
')
[[ -n "$version" ]] || { echo "could not determine the latest brave-origin version" >&2; exit 1; }

deb="brave-origin_${version}_amd64.deb"
url="$pool/pool/main/b/brave-origin/$deb"

workdir=$(mktemp -d "${TMPDIR:-/tmp}/ravnix-brave-origin.XXXXXX")
trap 'rm -rf "$workdir"' EXIT
curl -fsSL -o "$workdir/$deb" "$url"

hash=$(openssl dgst -sha256 -binary "$workdir/$deb" | base64)

cat <<EOF
version = "$version"
hash = "sha256-$hash"
url = "$url"
EOF
