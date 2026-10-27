# Packaged by writeShellApplication with a fixed PATH. Never run at build time.
set -Eeuo pipefail
fail() { echo "Error: $*" >&2; exit 1; }
partition_path() {
 if [[ $1 == *[0-9] ]]; then printf '%sp%s\n' "$1" "$2"; else printf '%s%s\n' "$1" "$2"; fi
}
validate_username() {
 [[ $1 =~ ^[a-z_][a-z0-9_-]{0,31}$ && $1 != root && $1 != ravnix && $1 != nixos ]] || fail 'Invalid or reserved username.'
 ! getent passwd "$1" >/dev/null || fail 'Username already exists; choose another.'
}
validate_disk() {
 local disk=$1 mounts types read_only size name holders
 [[ -b $disk ]] || fail 'Select a block device.'
 [[ $(lsblk -dn -o TYPE "$disk") == disk ]] || fail 'Select a whole disk, not a partition.'
 read_only=$(lsblk -dn -o RO "$disk") || fail 'Cannot inspect disk.'
 [[ $read_only == 0 ]] || fail 'Disk is read-only.'
 size=$(lsblk -bdn -o SIZE "$disk") || fail 'Cannot inspect size.'
 [[ $size =~ ^[0-9]+$ ]] || fail 'Cannot read numeric disk size.'
 ((size >= 16 * 1024 * 1024 * 1024)) || fail 'Disk must be at least 16 GiB.'
 mounts=$(lsblk -nr -o MOUNTPOINTS "$disk") || fail 'Cannot inspect mounts.'
 [[ -z ${mounts//[[:space:]]/} ]] || fail 'Disk has mounted filesystems or active swap; it may be the live USB.'
 types=$(lsblk -nr -o TYPE "$disk") || fail 'Cannot inspect disk children.'
 while IFS= read -r type; do
  [[ $type == disk || $type == part ]] || fail 'Active LVM/encryption/RAID device found.'
 done <<< "$types"
 while IFS= read -r name; do
  if [[ -d /sys/class/block/$name/holders ]]; then
   holders=$(find "/sys/class/block/$name/holders" -mindepth 1 -maxdepth 1 -print -quit) || fail 'Cannot inspect disk holders.'
   [[ -z $holders ]] || fail 'Disk has active device holders.'
  fi
 done < <(lsblk -nr -o KNAME "$disk")
}
unmount_target() {
 local attempt
 for attempt in 1 2 3; do
  if umount -R /mnt; then return 0; fi
  [[ $attempt == 3 ]] || sleep 1
 done
 findmnt -R /mnt >&2 || true
 fail 'Cannot unmount /mnt. Inspect remaining mounts before rebooting; no forced unmount was attempted.'
}
main() {
 if [[ ${1:-} == --help || ${1:-} == -h ]]; then
  echo 'Usage: sudo ravnix-install'
  echo 'Text installer: dedicated whole disk, GPT/ext4, BIOS or UEFI; internet; 16 GiB minimum.'
  echo 'Erases selected disk only after exact confirmation. No dual boot, encryption, LVM or RAID.'
  return
 fi
 (($# == 0)) || fail 'Unknown option. Use --help.'
 [[ $EUID == 0 ]] || fail 'Run sudo ravnix-install.'
 [[ -t 0 && -t 1 ]] || fail 'Interactive terminal required.'
 [[ -f /etc/ravnix/live && -f /etc/ravnix/source/flake.lock ]] || fail 'Run from the RAVNIX live ISO.'
 local mounts entries mode=bios disk hostname username timezone answer identity current root efi bootdevice
 mounts=$(findmnt -rn -o TARGET) || fail 'Cannot inspect mounts.'
 if printf '%s\n' "$mounts" | grep -Eq '^/mnt(/|$)'; then fail '/mnt is already in use; inspect mounts first.'; fi
 [[ ! -L /mnt ]] || fail '/mnt must not be a symlink.'
 mkdir -p /mnt
 entries=$(find /mnt -mindepth 1 -maxdepth 1 -print -quit) || fail 'Cannot inspect /mnt.'
 [[ -z $entries ]] || fail '/mnt must be empty.'
 curl -fsSI --max-time 20 https://cache.nixos.org/nix-cache-info >/dev/null || fail 'Nix cache HTTPS unavailable; configure networking with nmtui first.'
 # The pinned Nixpkgs source is fetched from github.com during flake evaluation;
 # verify both hosts before anything destructive happens.
 curl -fsSI --max-time 20 https://github.com/ >/dev/null || fail 'github.com unreachable; the pinned Nixpkgs source cannot be fetched. Configure networking with nmtui first.'
 [[ ! -d /sys/firmware/efi ]] || mode=uefi
 echo "RAVNIX text installer — detected boot mode: $mode"
 lsblk -d -o NAME,SIZE,MODEL,TRAN,RO
 read -r -p 'Target whole disk: ' disk
 disk=$(readlink -f -- "$disk") || fail 'Cannot resolve disk.'
 validate_disk "$disk"
 identity=$(lsblk -bdn -o MAJ:MIN,SIZE,MODEL,SERIAL "$disk") || fail 'Cannot inspect disk identity.'
 read -r -p 'Hostname: ' hostname
 [[ $hostname =~ ^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$ ]] || fail 'Invalid hostname.'
 read -r -p 'Username: ' username
 validate_username "$username"
 read -r -p 'Timezone [Europe/Warsaw]: ' timezone
 timezone=${timezone:-Europe/Warsaw}
 [[ $timezone != /* && $timezone != *..* && $timezone =~ ^[a-zA-Z0-9_+/-]+$ && -f /etc/zoneinfo/$timezone ]] || fail 'Invalid timezone.'
 printf '\nSelected disk (ALL DATA WILL BE LOST):\n'
 lsblk -d -o NAME,SIZE,MODEL,SERIAL "$disk"
 echo "Install RAVNIX ($mode), hostname $hostname, user $username, timezone $timezone."
 read -r -p "Type ERASE $disk to continue: " answer
 [[ $answer == "ERASE $disk" ]] || fail 'Cancelled; disk was not modified.'
 validate_disk "$disk"
 current=$(lsblk -bdn -o MAJ:MIN,SIZE,MODEL,SERIAL "$disk") || fail 'Cannot inspect disk identity.'
 [[ $identity == "$current" ]] || fail 'Disk identity changed; cancelled.'
 [[ $disk =~ ^/dev/[a-zA-Z0-9/_.:+-]+$ ]] || fail 'Unsupported device path.'
 bootdevice=$disk
 # BIOS GRUB must keep working when Linux changes /dev/sdX enumeration.
 if [[ $mode == bios ]]; then
  local link
  for link in /dev/disk/by-id/*; do
   [[ -L $link && $link != *-part[0-9]* && $link =~ ^/dev/[a-zA-Z0-9/_.:+-]+$ ]] || continue
   if [[ $(readlink -f "$link") == "$disk" ]]; then bootdevice=$link; break; fi
  done
 fi
 parted -s "$disk" mklabel gpt
 if [[ $mode == uefi ]]; then
  parted -s "$disk" mkpart ESP fat32 1MiB 513MiB
  parted -s "$disk" set 1 esp on
  parted -s "$disk" mkpart primary ext4 513MiB 100%
 else
  parted -s "$disk" mkpart BIOSBOOT 1MiB 3MiB
  parted -s "$disk" set 1 bios_grub on
  parted -s "$disk" mkpart primary ext4 3MiB 100%
 fi
 partprobe "$disk"
 udevadm settle
 root=$(partition_path "$disk" 2)
 efi=$(partition_path "$disk" 1)
 [[ $mode != uefi ]] || mkfs.fat -F 32 -n RAVNIX_EFI "$efi"
 mkfs.ext4 -F -L RAVNIX_ROOT "$root"
 mount -t ext4 "$root" /mnt
 if [[ $mode == uefi ]]; then mkdir -p /mnt/boot/efi; mount -t vfat "$efi" /mnt/boot/efi; fi
 mkdir -p /mnt/etc/nixos
 cp -R /etc/ravnix/source/. /mnt/etc/nixos/
 chmod -R u+w /mnt/etc/nixos
 nixos-generate-config --root /mnt >/dev/null
 cat > /mnt/etc/nixos/host.nix <<HOST
{ ... }: {
  networking.hostName = "$hostname";
  time.timeZone = "$timezone";
  users.users."$username" = {
    isNormalUser = true;
    extraGroups = [ "wheel" "networkmanager" ];
  };
  boot.loader.grub = {
    enable = true;
    device = "$(if [[ $mode == uefi ]]; then echo nodev; else echo "$bootdevice"; fi)";
    efiSupport = $(if [[ $mode == uefi ]]; then echo true; else echo false; fi);
    efiInstallAsRemovable = $(if [[ $mode == uefi ]]; then echo true; else echo false; fi);
  };
  boot.loader.efi = { canTouchEfiVariables = false; efiSysMountPoint = "/boot/efi"; };
}
HOST
 # Flakes use host.nix + hardware-configuration.nix. The upstream channel-style
 # configuration is not used; replace it with an equivalent import for clarity.
 cat > /mnt/etc/nixos/configuration.nix <<'CONFIG'
{ ... }: { imports = [ ./modules/base.nix ./hardware-configuration.nix ./host.nix ]; }
CONFIG
 echo 'Building and installing the pinned RAVNIX configuration...'
 nixos-install --root /mnt --flake path:/mnt/etc/nixos#ravnix --no-root-passwd
 echo "Set password for $username (required for login and sudo):"
 nixos-enter --root /mnt --command "passwd $username"
 # A successful passwd command is required before unmounting or offering reboot.
 sync
 unmount_target
 echo 'RAVNIX installation complete. Remove the ISO/USB after powering off.'
 read -r -p 'Reboot now? [y/N]: ' answer
 if [[ $answer == y || $answer == Y ]]; then reboot; fi
}
main "$@"
