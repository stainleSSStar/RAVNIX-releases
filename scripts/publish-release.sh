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
p=Path(sys.argv[1])
parts=sorted(p.glob('*.iso.part-*'))
assert parts, 'no ISO parts found in the draft'
assert not list(p.glob('*.iso')), 'the draft must not contain an unsplit image'
expected={}
for line in (p/'SHA256SUMS').read_text().splitlines():
    if line.strip():
        digest,name=line.split()
        expected[Path(name).name]=digest
assert set(expected)=={part.name for part in parts}, 'SHA256SUMS does not match the parts'
for part in parts:
    with part.open('rb') as f:
        assert hashlib.file_digest(f,'sha256').hexdigest()==expected[part.name], part.name
# The reassembled image must match the digest of the image that was tested.
whole=hashlib.sha256()
for part in parts:
    with part.open('rb') as f:
        for chunk in iter(lambda: f.read(8*1024*1024), b''):
            whole.update(chunk)
assert whole.hexdigest()==(p/'ISO-SHA256').read_text().split()[0], 'reassembled image does not match ISO-SHA256'
assert (p/'VM-TESTS.txt').read_text().startswith('PASS: BIOS and UEFI live, KDE Plasma desktop, text installation, password login, rebuild and reboot.\n')
assert (p/'build-info.txt').is_file() and (p/'flake.lock').is_file()
assert (p/'PARTS.txt').is_file()
print(f'{len(parts)} parts verified, reassembled image matches ISO-SHA256, full BIOS/UEFI test report verified.')
PY
gh release create "$tag" --repo "$release_repo" --draft --latest=false \
 --title "RAVNIX 26.05 Desktop (${tag})" \
 --notes "NixOS 26.05 derivative with KDE Plasma 6, the Purple Neon theme, a custom wallpaper and a branded GRUB bootloader. Fish shell, graphical networking, Brave Origin, Midnight Commander, btop and fastfetch are preinstalled. Both installers are included: the standard NixOS graphical installer (Calamares) and RAVNIX's own text installer. The image is published in parts because GitHub limits a release asset to 2 GiB: run 'cat ravnix-26.05-x86_64.iso.part-* > ravnix-26.05-x86_64.iso' and verify it against ISO-SHA256. BIOS and UEFI live, actual installation, password-required login/sudo, pinned rebuild and reboot passed. See build-info.txt for the exact source, PARTS.txt, GUIDE.md, VM-TESTS.txt and SHA256SUMS. Physical hardware and Secure Boot are outside VM coverage."
for asset in "$directory"/*; do
 [[ -s $asset ]] || continue
 gh release upload "$tag" "$asset" --repo "$release_repo"
done
gh release edit "$tag" --repo "$release_repo" --draft=false --prerelease=false --latest=true
gh release view "$tag" --repo "$release_repo" --json url --jq .url
