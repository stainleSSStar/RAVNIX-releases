# RAVNIX

Minimal **x86_64 NixOS 26.05 console distribution**, following RAVNUX's small
base/live-only installer/tested-release approach. **TTY only: no graphical stack.**

- Fish and NetworkManager for Ethernet/Wi-Fi, essential firmware and CPU microcode.
- Explicit minimal NixOS configuration with a pinned Nixpkgs revision and lockfile.
- Text installer for a dedicated whole disk: BIOS/GPT or UEFI/GPT, ext4 and GRUB.
- Real ISO and installation tests in both firmware modes before release publication.
- Password login/sudo, locked root, no installed autologin or SSH server.
- NixOS configuration generations and rollback; no automatic upgrades or cleanup.

[Live and installation guide](docs/GUIDE.md). The ISO includes `ravnix-guide`.

## Build

On x86_64 Linux with Nix and flakes enabled:

```sh
nix build .#iso
```

The ISO is `result/iso/ravnix-26.05-x86_64.iso`. Source checks and evaluation:

```sh
python3 scripts/check.py
python3 -m unittest discover -s tests -v
nix flake check --no-build
```

Push/PR runs validation. **Actions → Build RAVNIX ISO → Run workflow** builds
and tests the actual ISO and text installer in BIOS and UEFI, then publishes a
release in **this repository**. It preserves the repository's visibility and
uses GitHub Releases, not the quota-limited Actions artifact store. Uploads stay
in a draft until every file is present. Failed builds/tests do not publish.
`publish_release=false` allows a non-publishing test run.

Each release includes ISO, SHA256SUMS, exact source/Nixpkgs revisions, store-path
manifest, closure size, guide, lockfile and VM/build logs. Verify SHA256SUMS before
writing the ISO. The firmware/kernel coverage retains necessary dependencies;
Nix store path counts are not directly comparable to Arch package counts.

Install from the booted ISO with `sudo ravnix-install`. **The installer erases
all data on the selected disk after exact confirmation.** Internet and a dedicated
16 GiB+ disk are required. No dual boot, encryption/LVM/RAID or Secure Boot setup.
Physical hardware still needs validation on the target machines.

The repository is a NixOS derivative, not an official NixOS release. Source code
is MIT; Nixpkgs and included software retain their respective licenses.
