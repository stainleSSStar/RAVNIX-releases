# Packaged by writeShellApplication with a fixed PATH. Never run at build time.
set -Eeuo pipefail
# The smallest disk the installed system fits on: the desktop closure is about
# ten gigabytes, the rest is the filesystem, the ramdisk and the spare room the
# package manager needs.
MINIMUM_DISK_SIZE=$((16 * 1024 * 1024 * 1024))
fail() { echo "Error: $*" >&2; exit 1; }
partition_path() {
 if [[ $1 == *[0-9] ]]; then printf '%sp%s\n' "$1" "$2"; else printf '%s%s\n' "$1" "$2"; fi
}
validate_username() {
 [[ $1 =~ ^[a-z_][a-z0-9_-]{0,31}$ && $1 != root && $1 != ravnix && $1 != nixos ]] || fail 'Invalid or reserved username.'
 ! getent passwd "$1" >/dev/null || fail 'Username already exists; choose another.'
}
kernel_params_nix() {
 # NixOS wants one parameter per list entry, and an entry must not contain
 # spaces unless they are inside quotes.
 local parameters=$1 parameter
 [[ -n $parameters ]] || return 0
 printf '  boot.kernelParams = ['
 for parameter in $parameters; do printf ' "%s"' "$parameter"; done
 printf ' ];\n'
}
parse_arguments() {
 kernel_params=''
 interactive=1
 disk='' root='' hostname='' username='' timezone=''
 while (($# > 0)); do
  case $1 in
   --kernel-params)
    (($# >= 2)) || fail 'Missing value for --kernel-params.'
    kernel_params=$2
    shift 2
    ;;
   --kernel-params=*)
    kernel_params=${1#--kernel-params=}
    shift
    ;;
   --non-interactive)
    interactive=0
    shift
    ;;
   --disk)
    (($# >= 2)) || fail 'Missing value for --disk.'
    disk=$2
    shift 2
    ;;
   --disk=*)
    disk=${1#--disk=}
    shift
    ;;
   --root)
    (($# >= 2)) || fail 'Missing value for --root.'
    root=$2
    shift 2
    ;;
   --root=*)
    root=${1#--root=}
    shift
    ;;
   --hostname)
    (($# >= 2)) || fail 'Missing value for --hostname.'
    hostname=$2
    shift 2
    ;;
   --hostname=*)
    hostname=${1#--hostname=}
    shift
    ;;
   --username)
    (($# >= 2)) || fail 'Missing value for --username.'
    username=$2
    shift 2
    ;;
   --username=*)
    username=${1#--username=}
    shift
    ;;
   --timezone)
    (($# >= 2)) || fail 'Missing value for --timezone.'
    timezone=$2
    shift 2
    ;;
   --timezone=*)
    timezone=${1#--timezone=}
    shift
    ;;
   *) fail 'Unknown option. Use --help.';;
  esac
 done
 # The parameters end up in a Nix string, so only plain characters are allowed.
 [[ -z $kernel_params || $kernel_params =~ ^[A-Za-z0-9=,.:/+@%_-]+(\ [A-Za-z0-9=,.:/+@%_-]+)*$ ]] || fail 'Kernel parameters contain unsupported characters.'
 if ((interactive == 0)); then
  # The graphical installer prepares the disk and collects the answers, so the
  # values are given instead of asked for.
  [[ -n $root && -n $disk && -n $hostname && -n $username ]] || fail 'The automated installation needs --root, --disk, --hostname and --username.'
  [[ $root == /* ]] || fail 'The mount point of the target has to be an absolute path.'
  [[ $disk == /dev/* ]] || fail 'The target disk has to be a device.'
 else
  [[ -z $disk && -z $root && -z $hostname && -z $username && -z $timezone ]] || fail 'These options belong to the automated installation.'
 fi
}
validate_disk() {
 local disk=$1 mounts types read_only size name holders
 [[ -b $disk ]] || fail 'Select a block device.'
 [[ $(lsblk -dn -o TYPE "$disk") == disk ]] || fail 'Select a whole disk, not a partition.'
 read_only=$(lsblk -dn -o RO "$disk") || fail 'Cannot inspect disk.'
 [[ $read_only == 0 ]] || fail 'Disk is read-only.'
 size=$(lsblk -bdn -o SIZE "$disk") || fail 'Cannot inspect disk size.'
 [[ $size =~ ^[0-9]+$ ]] || fail 'Cannot read numeric disk size.'
 ((size >= MINIMUM_DISK_SIZE)) || fail 'Disk must be at least 16 GiB.'
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
boot_device() {
 # BIOS GRUB must keep working when Linux changes /dev/sdX enumeration, so the
 # installation uses the persistent disk identifier when there is one.
 local disk=$1 link
 [[ $disk == /dev/* ]] || fail 'Unsupported device path.'
 if [[ $2 == bios ]]; then
  for link in /dev/disk/by-id/*; do
   [[ -L $link && $link != *-part[0-9]* && $link =~ ^/dev/[a-zA-Z0-9/_.:+-]+$ ]] || continue
   if [[ $(readlink -f "$link") == "$disk" ]]; then printf '%s\n' "$link"; return 0; fi
  done
 fi
 printf '%s\n' "$disk"
}
host_configuration() {
 # The configuration of the machine: the answers of the installer and the
 # bootloader that matches the layout of the disk.
 local hostname=$1 username=$2 timezone=$3 mode=$4 device=$5
 cat <<HOST
{ ... }: {
  networking.hostName = "$hostname";
  time.timeZone = "$timezone";
  users.users."$username" = {
    isNormalUser = true;
    extraGroups = [ "wheel" "networkmanager" "video" "render" "input" "lp" "scanner" "dialout" ];
  };
  boot.loader.grub = {
    enable = true;
    device = "$(if [[ $mode == uefi ]]; then echo nodev; else echo "$device"; fi)";
    efiSupport = $(if [[ $mode == uefi ]]; then echo true; else echo false; fi);
    efiInstallAsRemovable = $(if [[ $mode == uefi ]]; then echo true; else echo false; fi);
  };
  boot.loader.efi = { canTouchEfiVariables = false; efiSysMountPoint = "/boot/efi"; };
$(kernel_params_nix "${kernel_params:-}")}
HOST
}
write_configuration() {
 # The configuration of the installed system: the pinned source tree, the
 # hardware description of the machine and the answers of the installer.
 local root=$1 hostname=$2 username=$3 timezone=$4 mode=$5 device=$6
 mkdir -p "$root/etc/nixos"
 cp -R /etc/ravnix/source/. "$root/etc/nixos/"
 chmod -R u+w "$root/etc/nixos"
 nixos-generate-config --root "$root" >/dev/null
 host_configuration "$hostname" "$username" "$timezone" "$mode" "$device" > "$root/etc/nixos/host.nix"
 cat > "$root/etc/nixos/configuration.nix" <<'CONFIG'
{ ... }: { imports = [ ./modules/base.nix ./hardware-configuration.nix ./host.nix ]; }
CONFIG
}
install_system() {
 # The installation copies roughly ten gigabytes into the new store and needs
 # the network for the paths that are not in the live image. One interrupted
 # transfer must not abort an installation that has already erased the disk:
 # nix gets longer timeouts for a slow or flaky connection, it retries a
 # failed download more often than the default five times, and if a substitute
 # still cannot be fetched it builds that single path from source instead of
 # failing the whole installation. The live image already carries the
 # bootloader and the initial ramdisk tools, so in practice nothing has to be
 # downloaded at all.
 local root=$1
 echo 'Building and installing the pinned RAVNIX configuration...'
 nixos-install --root "$root" --flake "path:$root/etc/nixos#ravnix" --no-root-passwd \
  --option fallback true --option connect-timeout 30 \
  --option stalled-download-timeout 120 --option download-attempts 10
}
check_live_medium() {
 [[ -f /etc/ravnix/live && -f /etc/ravnix/source/flake.lock ]] || fail 'Run from the RAVNIX live ISO.'
}
check_prepared_layout() {
 # The graphical installer prepares the disk. RAVNIX installs a layout that the
 # bootloader of the distribution can read: ext4 for the root, an EFI system
 # partition at /boot/efi on a UEFI machine and a partition for the BIOS
 # bootloader on a GPT disk. A layout that does not match would leave a system
 # that does not boot, so the installation stops here instead.
 local root=$1 disk=$2 mode=$3 fstype source size esp table
 fstype=$(findmnt -rn -o FSTYPE --target "$root" 2>/dev/null | head -n1) || true
 [[ $fstype == ext4 ]] || fail "The target filesystem is ${fstype:-unknown}; RAVNIX installs ext4."
 source=$(findmnt -rn -o SOURCE --target "$root" 2>/dev/null | head -n1) || true
 [[ $source != /dev/mapper/* ]] || fail 'The target is encrypted; RAVNIX does not unlock an encrypted root.'
 size=$(lsblk -bdn -o SIZE "$disk") || fail 'Cannot inspect the size of the target disk.'
 [[ $size =~ ^[0-9]+$ ]] || fail 'Cannot read the size of the target disk.'
 ((size >= MINIMUM_DISK_SIZE)) || fail 'The target disk is smaller than 16 GiB.'
 if [[ $mode == uefi ]]; then
  # The bootloader of a UEFI system is written to the EFI system partition, so
  # it has to be mounted at the place where the configuration expects it.
  findmnt -rn -o TARGET | grep -qx "$root/boot/efi" || fail "The EFI system partition is not mounted at $root/boot/efi."
  esp=$(findmnt -rn -o FSTYPE --target "$root/boot/efi" 2>/dev/null | head -n1) || true
  [[ $esp == vfat ]] || fail "The EFI system partition at $root/boot/efi is ${esp:-unknown}; it has to be a FAT filesystem."
  return 0
 fi
 # GRUB writes the BIOS bootloader into a partition of its own on a GPT disk.
 # A disk with an MBR partition table carries it in the space between the MBR
 # and the first partition.
 table=$(parted -s "$disk" print 2>/dev/null) || fail "Cannot read the partition table of $disk."
 if [[ $table != *"Partition Table: msdos"* ]]; then
  [[ $table == *bios_grub* ]] || fail "The disk has no partition for the BIOS bootloader; GRUB cannot be installed on it."
 fi
}
check_target_mount() {
 # The graphical installer formats the disk and mounts it empty, so the target
 # has no /etc yet. The mount point is what tells a prepared target from an
 # empty directory, and a target that already holds an installation is refused.
 local root=$1
 [[ -d $root ]] || fail "The target $root does not exist."
 findmnt -rn -o TARGET | grep -Eq "^${root}(/|$)" || fail "The target $root is not a mount point."
 [[ ! -e $root/etc/NIXOS ]] || fail "The target $root already holds a NixOS installation."
}
automated_installation() {
 # The graphical installer has already partitioned the disk, mounted the
 # target and collected the answers. Only the installation itself is left.
 local mode=bios device
 check_live_medium
 [[ $EUID == 0 ]] || fail 'Run as root.'
 check_target_mount "$root"
 if [[ ! -d /sys/firmware/efi ]]; then mode=bios; else
  mode=uefi
 fi
 check_prepared_layout "$root" "$disk" "$mode"
 validate_username "$username"
 [[ $hostname =~ ^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$ ]] || fail 'Invalid hostname.'
 timezone=${timezone:-Europe/Warsaw}
 [[ $timezone != /* && $timezone != *..* && $timezone =~ ^[a-zA-Z0-9_+/-]+$ && -f /etc/zoneinfo/$timezone ]] || fail 'Invalid timezone.'
 [[ ! -d /sys/firmware/efi ]] || mode=uefi
 device=$(boot_device "$disk" "$mode")
 write_configuration "$root" "$hostname" "$username" "$timezone" "$mode" "$device"
 install_system "$root"
 sync
 echo "RAVNIX installation complete on $disk."
}
interactive_installation() {
 local mounts entries mode=bios hostname username timezone answer identity current root efi bootdevice
 check_live_medium
 [[ $EUID == 0 ]] || fail 'Run sudo ravnix-install.'
 [[ -t 0 && -t 1 ]] || fail 'Interactive terminal required.'
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
 bootdevice=$(boot_device "$disk" "$mode")
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
 write_configuration /mnt "$hostname" "$username" "$timezone" "$mode" "$bootdevice"
 install_system /mnt
 echo "Set password for $username (required for login and sudo):"
 nixos-enter --root /mnt --command "passwd $username"
 # A successful passwd command is required before unmounting or offering reboot.
 sync
 unmount_target
 echo 'RAVNIX installation complete. Remove the ISO/USB after powering off.'
 read -r -p 'Reboot now? [y/N]: ' answer
 if [[ $answer == y || $answer == Y ]]; then reboot; fi
}
main() {
 if [[ ${1:-} == --help || ${1:-} == -h ]]; then
  echo 'Usage: sudo ravnix-install [--kernel-params "<parameters>"]'
  echo 'Text installer: dedicated whole disk, GPT/ext4, BIOS or UEFI; internet; 16 GiB minimum.'
  echo 'Erases selected disk only after exact confirmation. No dual boot, encryption, LVM or RAID.'
  echo 'Extra kernel parameters, for example "console=ttyS0,115200n8" for a serial console.'
  echo ''
  echo 'The graphical installer prepares the disk and calls the installation with:'
  echo '  ravnix-install --non-interactive --root <mount point> --disk <device> --hostname <name> --username <name> [--timezone <zone>]'
  return
 fi
 parse_arguments "$@"
 if ((interactive == 0)); then
  automated_installation
 else
  interactive_installation
 fi
}
main "$@"
