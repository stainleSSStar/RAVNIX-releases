# RAVNIX console guide

RAVNIX is a minimal x86_64 NixOS 26.05 derivative. It contains Fish,
NetworkManager (Ethernet and Wi-Fi), firmware, Nix, systemd and the normal
console/system tools. There is no graphical stack, desktop, display manager,
browser, audio server, Bluetooth service, SSH server or application bundle.
Secure Boot is not configured. Use BIOS or x86_64 UEFI with Secure Boot off.

## Live session

The live medium logs in as `ravnix` with passwordless sudo, on local consoles
only. Root is locked and no SSH server is enabled. Connect Ethernet or run
`nmtui`; `nmcli device status` shows network state. Run `ravnix-guide` to read
this guide offline. Installation needs internet access to the Nix binary cache
and the pinned Nixpkgs source. The live session itself is offline-capable.

## Text installation

Boot the ISO in the intended BIOS/UEFI mode, open the console, connect networking:

```sh
sudo ravnix-install
```

The installer asks for the **whole target disk**, hostname, new username and
timezone (default Europe/Warsaw). It displays the disk identity and requires
`ERASE /dev/...` matching the selected device exactly. **All existing data and
partitions on that disk will be erased.** Do not choose the live USB.
Mounted disks, active swap, read-only disks and active LVM/RAID/encryption
mappings are rejected. A dedicated disk of at least 16 GiB is required.

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

After reboot, remove the live medium. Log in with the new account. There is no
autologin, `ravnix` account, live guide or installer command in the installed PATH.

## Configuration, rebuild and rollback

`/etc/nixos/host.nix` contains your hostname, timezone, user and bootloader.
`hardware-configuration.nix` is generated from the actual machine, including UUIDs.
`modules/base.nix` defines the small shared system. `flake.nix` and `flake.lock`
pin Nixpkgs. Local configuration files remain writable; no private GitHub access
is needed for future rebuilds. Keep a backup of `/etc/nixos`.

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
`less`, `curl`, `lspci`, `lsusb`, `ethtool` and `smartctl` are also included.
Use `ip address`, `nmcli device status`, `journalctl -b` and `dmesg` to inspect
networking and driver/firmware messages. Kernel drivers, redistributable firmware
and Intel/AMD microcode cover common PC hardware; proprietary-only or unusual
hardware may need additional configuration. No driver collection can guarantee
every device. No development environment is preinstalled.

## Verification limits

Release CI boots the actual ISO in BIOS and UEFI, drives the text installer on
blank SATA/NVMe disks, boots the installed system, checks Fish, networking,
password login, sudo, locked root, absence of GUI and live tools, rebuilds the
same pinned configuration, and boots again. VM coverage does not establish
compatibility with every physical network adapter, storage controller or machine.
