# RAVNIX desktop guide

RAVNIX is an x86_64 NixOS 26.05 derivative with **KDE Plasma 6** as its desktop.
It ships the Purple Neon theme (deep violet with pink and green accents), a
custom 4K wallpaper, Fish as the shell, NetworkManager with a graphical
network applet, the standard NixOS graphical installer and RAVNIX's own text
installer. Secure Boot is not configured. Use BIOS or x86_64 UEFI with Secure
Boot off.

## Getting the image

Releases are published in
**[RAVNIX-releases](https://github.com/stainleSSStar/RAVNIX-releases/releases)**.
GitHub refuses a single release asset of 2 GiB or more and the desktop image is
about 3.7 GB, so the image is published in parts:

```sh
cat ravnix-26.05-x86_64.iso.part-* > ravnix-26.05-x86_64.iso
sha256sum -c ISO-SHA256
```

`sha256sum -c SHA256SUMS` checks the parts themselves before reassembling them.

## Live session

The live medium boots into the Plasma desktop and logs in as `ravnix`
automatically. The same account is available on the serial console and on the
virtual consoles, with passwordless sudo. Root is locked and no SSH server is
enabled.

* **Network** — plug in Ethernet or use the network applet in the system tray;
  `nmcli device status` and `nmtui` still work from the terminal.
* **Shell** — Fish, in Konsole as well as on the console.
* **Browser** — Brave Origin, the stripped-down Brave build that is free on
  Linux. It is also the default handler for web links and files.
* **Tools** — Midnight Commander, btop and fastfetch (with the RAVNIX "R"
  logo). `ravnix-guide` prints this guide offline.
* **Installers** — the desktop has shortcuts for both installers: *Install
  RAVNIX* (the text installer below) and *Install NixOS* (the standard
  graphical Calamares installer).

Installation works without an internet connection: the live medium already
carries the bootloader, the tools that build the initial ramdisk and the
pinned Nixpkgs source, so everything the installation needs is on the medium
itself. Only a few kilobytes of rendered files, such as the sudoers file,
come from the Nix binary cache; if the cache cannot be reached, they are
built locally instead. The live session itself is offline-capable as well.

## Appearance

The wallpaper, the colour scheme and the greeter theme are RAVNIX specific:

* The **greeter** (the screen before login) already uses the RAVNIX wallpaper
  and the Purple Neon panel, so nothing looks stock before you log in.
* The **desktop** applies the same wallpaper and colour scheme when the Plasma
  shell starts.
* **Konsole** uses the RAVNIX colour scheme with a slightly transparent
  background.
* Every new account gets the RAVNIX profile in its home directory: the
  Konsole profile, the colour scheme, the btop theme and the fastfetch
  configuration with the RAVNIX "R" logo. Files that already exist are left
  alone, so an account can change its own configuration.

To change them, edit `modules/desktop.nix` and rebuild. The assets live in
`assets/`: `ravnix-wallpaper.jpg`, `RAVNIX-PurpleNeon.colorscheme` and the
`assets/sddm-ravnix/` greeter theme.

## Text installation

Boot the ISO in the intended BIOS/UEFI mode and run the installer from the
desktop shortcut, or from a terminal:

```sh
sudo ravnix-install
```

The installer asks for the **whole target disk**, hostname, new username and
timezone (default Europe/Warsaw). It displays the disk identity and requires
`ERASE /dev/...` matching the selected device exactly. **All existing data and
partitions on that disk will be erased.** Do not choose the live USB.
Mounted disks, active swap, read-only disks and active LVM/RAID/encryption
mappings are rejected. A dedicated disk of at least 16 GiB is required.

For a headless machine, add the parameters of the kernel command line, for
example a serial console:

```sh
sudo ravnix-install --kernel-params "console=tty0 console=ttyS0,115200n8"
```

UEFI: GPT, 512 MiB FAT32 ESP mounted at `/boot/efi`, remaining space ext4.
BIOS: GPT, 2 MiB BIOS boot partition, remaining space ext4.
GRUB uses removable-media fallback for UEFI without modifying firmware NVRAM.
Root filesystem references use UUIDs; BIOS uses a persistent disk ID when available.
There is no dual boot, encryption, RAID, LVM, separate home or swap setup.

Installation writes a hardware-specific configuration to `/etc/nixos`, installs
the pinned system, then asks twice for the new user's password. Root stays locked.
The installed user belongs to wheel; sudo requires that password. Passwords are
set interactively and are not written into Nix expressions or the world-readable
Nix store. Rebuilds preserve password changes (`users.mutableUsers = true`).

On success the filesystems are unmounted without force/lazy unmount; reboot is
optional and defaults to no. On failure the installer stops and leaves the state
for inspection. Erased data cannot be restored by cancelling later.

After reboot, remove the live medium. Log in with the new account at the
RAVNIX greeter. There is no autologin, `ravnix` account, live guide or
installer command in the installed PATH.

## Graphical installation

The *Install NixOS* desktop shortcut starts the standard NixOS graphical
installer (Calamares). It offers partitioning, a user account, a locale and a
desktop choice, and installs NixOS with `nixos-install`. It installs a plain
NixOS configuration rather than the RAVNIX one — use *Install RAVNIX* when you
want the RAVNIX desktop, theme and preinstalled applications.

## Configuration, rebuild and rollback

`/etc/nixos/host.nix` contains your hostname, timezone, user and bootloader.
`hardware-configuration.nix` is generated from the actual machine, including UUIDs.
`modules/base.nix` defines the shared system and `modules/desktop.nix` the
desktop, theme and applications. `flake.nix` and `flake.lock` pin Nixpkgs. Local
configuration files remain writable; no private GitHub access is needed for
future rebuilds. Keep a backup of `/etc/nixos`.

After editing configuration:

```sh
sudo nixos-rebuild switch --flake path:/etc/nixos#ravnix
```

Roll back a configuration change:

```sh
sudo nixos-rebuild switch --rollback
```

Previous generations are also available in GRUB. Garbage collection and upgrades
are not automatic. The revision is pinned deliberately: security updates require
a reviewed change of the Nixpkgs input followed by a rebuild. `system.stateVersion`
is a compatibility setting; do not change it just to update packages.

Add optional tools declaratively to `environment.systemPackages` when needed.
Nano is installed for offline editing: `sudo nano /etc/nixos/host.nix`.
`less`, `curl`, `lspci`, `usbutils`, `ethtool` and `smartctl` are also included.
Use `ip address`, `nmcli device status`, `journalctl -b` and `dmesg` to inspect
networking and driver/firmware messages.

## Drivers

The image carries the full redistributable firmware collection, Intel and AMD
CPU microcode, 32-bit and 64-bit Mesa drivers with VA-API video acceleration,
PipeWire audio with ALSA routing, Bluetooth, printing, firmware updates
(fwupd) and every common storage/network boot driver. Kernel drivers,
redistributable firmware and microcode cover common PC hardware; proprietary-only
or unusual hardware may need additional configuration. No driver collection can
guarantee every device.

## Verification limits

Release CI boots the actual ISO in BIOS and UEFI, drives the text installer on
blank SATA/NVMe disks, boots the installed system, checks Fish, the Plasma
stack, the graphical network manager, Brave Origin, the branding assets,
password login, sudo, locked root, rebuilds the same pinned configuration, and
boots again. VM coverage does not establish compatibility with every physical
network adapter, storage controller or machine.
