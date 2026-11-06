#!/usr/bin/env bash
# Verify that the installation can run without a network connection and
# without a compiler.
#
# The installed system is built from the same modules as the live image, plus
# a bootloader configuration and the generated hardware description. The live
# image carries the whole desktop closure, so the installation mostly copies
# it. Everything the installation has to build itself is a configuration
# artefact: a rendered file such as the sudoers file, a systemd unit, the
# initial ramdisk or the system profile. Their inputs are small scripts that
# are part of the live image, so nix rebuilds them locally in a few minutes.
#
# Anything else is a package. Building a package needs its source and a
# compiler, and neither is in the live image, so the installation would have
# to download the source and compile it. That is slow on real hardware and
# impossible without a network connection. This check compares the paths that
# the installation has to build with the paths that the live image carries and
# reports every source that would have to be downloaded.
set -Eeuo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

# The rendered files are a few kilobytes; anything larger is a package.
limit=$((1024 * 1024))

mkdir -p "$tmp/etc-nixos"
cp -R "$root/." "$tmp/etc-nixos/"
rm -rf "$tmp/etc-nixos/.git"

# The same configuration the text installer writes into /mnt/etc/nixos.
cat > "$tmp/etc-nixos/hardware-configuration.nix" <<'HW'
{ ... }: {
  boot.initrd.availableKernelModules = [ "ahci" "ata_base" "ata_generic" "ata_piix" "libata" "sd_mod" "sr_mod" ];
  boot.initrd.kernelModules = [ ];
  boot.supportedFilesystems = [ "ext4" "vfat" ];
  fileSystems."/" = {
    device = "/dev/disk/by-label/RAVNIX_ROOT";
    fsType = "ext4";
  };
}
HW
cat > "$tmp/etc-nixos/configuration.nix" <<'CONFIG'
{ ... }: { imports = [ ./modules/base.nix ./hardware-configuration.nix ./host.nix ]; }
CONFIG

status=0
for mode in bios uefi; do
  echo "== plan for the $mode installation =="
  if [[ $mode == bios ]]; then
    device=/dev/sda
    efi=false
  else
    device=nodev
    efi=true
  fi
  cat > "$tmp/etc-nixos/host.nix" <<HOST
{ ... }: {
  networking.hostName = "ravnix-test";
  time.timeZone = "Europe/Warsaw";
  users.users."tester" = {
    isNormalUser = true;
    extraGroups = [ "wheel" "networkmanager" "video" "render" "input" "lp" "scanner" "dialout" ];
  };
  boot.kernelParams = [ "console=tty0 console=ttyS0,115200n8" ];
  boot.loader.grub = {
    enable = true;
    device = "$device";
    efiSupport = $efi;
    efiInstallAsRemovable = $efi;
  };
  boot.loader.efi = { canTouchEfiVariables = false; efiSysMountPoint = "/boot/efi"; };
}
HOST
  target=$(nix eval --raw "path:$tmp/etc-nixos#nixosConfigurations.ravnix.config.system.build.toplevel.drvPath")
  if [ -z "$target" ]; then
    echo "ERROR: the $mode installation could not be evaluated" >&2
    status=1
    continue
  fi
  nix derivation show --recursive "$target" > "$tmp/target.json"
  live=$(nix eval --raw .#nixosConfigurations.live.config.system.build.toplevel.drvPath)
  nix derivation show --recursive "$live" > "$tmp/live.json"
  if ! python3 "$root/scripts/check-install-plan.py" "$tmp/live.json" "$tmp/target.json" "$target" "$limit"; then
    echo "ERROR: the $mode installation depends on sources that the live image does not carry." >&2
    status=1
  fi
done
exit "$status"
