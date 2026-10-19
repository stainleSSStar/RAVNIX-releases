# RAVNIX

Minimal **x86_64 NixOS 26.05 console distribution**, following RAVNUX's small
base/live-only installer/tested-release approach. **TTY only: no graphical stack.**

- Fish and NetworkManager for Ethernet/Wi-Fi, essential firmware and CPU microcode.
- Offline Nano editor and basic PCI/USB, network and disk diagnostic tools.
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
and tests the actual ISO and text installer in BIOS and UEFI. With `stage_release`
enabled, only a successful test run uploads its files to a private draft in this
source repository. No Actions artifact storage is used. Failed tests do not stage
an ISO. The built-in token stays scoped to this repository; no personal credential
is stored in Actions.

To publish a tested draft to the public
**[RAVNIX-releases](https://github.com/stainleSSStar/RAVNIX-releases/releases)**
repository from a workstation with `gh` authenticated:

```sh
bash scripts/publish-release.sh v26.05-rBUILD_NUMBER
```

The command downloads the tested files, verifies their checksum and test report,
uploads a draft in the public releases repository, then publishes only after all
uploads succeed. The source repository stays private. `stage_release=false`
performs an ephemeral build/test without saving the ISO.

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
