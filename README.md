# RAVNIX

**x86_64 NixOS 26.05 distribution with KDE Plasma 6**, following RAVNUX's small
base/live-only installer/tested-release approach.

- **KDE Plasma 6** desktop with the RAVNIX *Purple Neon* theme: deep violet with
  pink and green accents, a custom 4K cyberpunk wallpaper and a branded greeter
  that is already themed before you log in.
- Fish as the shell, in Konsole (slightly transparent) and on every console.
- NetworkManager with a graphical applet for Ethernet and Wi-Fi.
- **Brave Origin** — the stripped-down Brave build that is free on Linux — plus
  Midnight Commander, btop and fastfetch with the RAVNIX "R" logo.
- Full redistributable firmware, CPU microcode, 32/64-bit Mesa with VA-API,
  PipeWire audio, Bluetooth, printing and firmware updates, so the same image
  works in a virtual machine and on real hardware.
- Two installers that install the **same** RAVNIX configuration: the graphical
  installer (Calamares, with the RAVNIX branding) and RAVNIX's own text
  installer.
- Explicit minimal NixOS configuration with a pinned Nixpkgs revision and lockfile.
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
# The release output, evaluated on every system: a check on another
# architecture does not reach it.
nix eval --raw .#packages.x86_64-linux.default.drvPath
```

Push/PR runs validation. **Actions → Build RAVNIX ISO → Run workflow** builds
and tests the actual ISO and text installer in BIOS and UEFI. With `stage_release`
enabled, only a successful test run uploads its files to a private draft in this
source repository. The tested image parts are additionally kept for 30 days as a
recoverable Actions artifact. Failed tests do not stage
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

Each release includes the ISO in parts, SHA256SUMS, exact source/Nixpkgs revisions,
store-path manifest, closure size, guide, lockfile and VM/build logs. The image is
larger than the 2 GiB limit GitHub puts on a single release asset, so it is
published as `ravnix-26.05-x86_64.iso.part-00` and friends. Reassemble it with:

```sh
cat ravnix-26.05-x86_64.iso.part-* > ravnix-26.05-x86_64.iso
sha256sum -c ISO-SHA256
```

The firmware/kernel coverage retains necessary dependencies;
Nix store path counts are not directly comparable to Arch package counts.

Install from the booted ISO with `sudo ravnix-install`, or use the *Install
RAVNIX graphically* desktop shortcut for the graphical installer. Both install
the same RAVNIX system. **The text installer erases all data on the selected
disk after exact confirmation.** The graphical installer prepares the same
layout on a BIOS and on a UEFI machine: a GPT disk with a 512 MiB FAT32 EFI
system partition at `/boot/efi`, a small partition for the BIOS bootloader and
ext4 for the rest.
The installation works without an internet connection, because the medium
carries the bootloader, the ramdisk tools and the pinned Nixpkgs source; a
dedicated 16 GiB+ disk is required. The installed system keeps the pinned
Nixpkgs source as well, so it can rebuild itself offline. Extra kernel
parameters, such as a serial
console for a headless machine, are passed with
`sudo ravnix-install --kernel-params "console=tty0 console=ttyS0,115200n8"`.
No dual boot,
encryption/LVM/RAID or Secure Boot setup. Physical hardware still needs
validation on the target machines.

## Layout

| Path | Purpose |
| --- | --- |
| `modules/base.nix` | Shared system: network, users, Fish, security policy, branding of GRUB, pinned Nixpkgs source |
| `modules/desktop.nix` | Plasma 6, Purple Neon theme, wallpaper, greeter theme, applications, drivers |
| `modules/live.nix` | Live medium: autologin, boot splash images, installer shortcuts |
| `modules/calamares/` | The graphical installer: its installation module, its partitioning and the RAVNIX branding |
| `assets/` | Wallpaper, colour schemes, greeter theme, fastfetch/btop branding, boot splash |
| `pkgs/brave-origin.nix` | Repackaging of the Brave Origin `.deb` (not in nixpkgs) |

Brave Origin is pinned by version and hash. To move to a newer release, run
`bash scripts/update-brave-origin.sh` and update `pkgs/brave-origin.nix`.

The repository is a NixOS derivative, not an official NixOS release. Source code
is MIT; Nixpkgs and included software retain their respective licenses.
