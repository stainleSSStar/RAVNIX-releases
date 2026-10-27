#!/usr/bin/env bash
# Promote only a successfully tested private build; never persist credentials.
set -euo pipefail
[[ $# == 1 && $1 =~ ^v26\.05-r[0-9]+$ ]] || { echo 'Usage: bash scripts/publish-release.sh v26.05-rNUMBER' >&2; exit 1; }
tag=$1
source_repo=stainleSSStar/RAVNIX
release_repo=stainleSSStar/RAVNIX-releases
directory=$(mktemp -d "${TMPDIR:-/tmp}/ravnix-publish.XXXXXX")
trap 'rm -rf "$directory"' EXIT
gh release download "$tag" --repo "$source_repo" --dir "$directory"
python3 - "$directory" <<'PY'
import hashlib,sys
from pathlib import Path
p=Path(sys.argv[1]); files=list(p.glob('*.iso'));assert len(files)==1 and files[0].stat().st_size>0
checksum,name=(p/'SHA256SUMS').read_text().strip().split()
assert Path(name).name==files[0].name
with files[0].open('rb') as f: assert hashlib.file_digest(f,'sha256').hexdigest()==checksum
assert (p/'VM-TESTS.txt').read_text().startswith('PASS: BIOS and UEFI live, text installation, password login, rebuild and reboot.\n')
assert (p/'build-info.txt').is_file() and (p/'flake.lock').is_file()
print('ISO checksum and full BIOS/UEFI test report verified.')
PY
gh release create "$tag" --repo "$release_repo" --draft --latest=false \
 --title "RAVNIX 26.05 TTY (${tag})" \
 --notes "Minimal console-only NixOS derivative: Fish, Ethernet/Wi-Fi networking and text installer. No graphical stack. BIOS and UEFI live, actual text installation, password-required login/sudo, pinned rebuild and reboot passed. See build-info.txt for exact source, GUIDE.md, VM-TESTS.txt and SHA256SUMS. Physical hardware and Secure Boot are outside VM coverage."
for asset in "$directory"/*; do
 [[ -s $asset ]] || continue
 gh release upload "$tag" "$asset" --repo "$release_repo"
done
gh release edit "$tag" --repo "$release_repo" --draft=false --prerelease=false --latest=true
gh release view "$tag" --repo "$release_repo" --json url --jq .url
