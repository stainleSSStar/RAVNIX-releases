{ config, lib, pkgs, modulesPath, ... }:
let
  source = lib.cleanSource ../.;
  installer = pkgs.writeShellApplication {
    name = "ravnix-install";
    runtimeInputs = with pkgs; [ coreutils util-linux parted dosfstools e2fsprogs gnugrep gnused curl ];
    text = builtins.readFile ../scripts/install.sh;
  };
  guide = pkgs.writeShellScriptBin "ravnix-guide" ''
    exec ${pkgs.coreutils}/bin/cat ${../docs/GUIDE.md}
  '';
in {
  imports = [ "${modulesPath}/installer/cd-dvd/iso-image.nix" ];
  hardware.enableAllHardware = true;
  # The bare ISO module only includes its own squashfs/ISO/tmpfs mounts.
  # Include exactly the filesystems our text installer creates.
  boot.supportedFilesystems = [ "ext4" "vfat" ];
  image.baseName = lib.mkForce "ravnix-26.05-x86_64";
  isoImage = {
    volumeID = "RAVNIX_2605";
    makeBiosBootable = true;
    makeEfiBootable = true;
    makeUsbBootable = true;
    squashfsCompression = "zstd -Xcompression-level 19";
  };
  boot.kernelParams = [ "console=tty0" "console=ttyS0,115200n8" ];
  boot.loader.grub.memtest86.enable = false;
  users.users.ravnix = {
    isNormalUser = true;
    extraGroups = [ "wheel" "networkmanager" ];
    initialHashedPassword = "";
  };
  services.getty.autologinUser = "ravnix";
  services.getty.helpLine = "RAVNIX LIVE: sudo ravnix-install | ravnix-guide | nmtui";
  security.sudo.wheelNeedsPassword = lib.mkForce false;
  system.tools = {
    nixos-enter.enable = true;
    nixos-generate-config.enable = true;
    nixos-install.enable = true;
  };
  environment.systemPackages = [ installer guide ];
  environment.etc."ravnix/source".source = source;
  environment.etc."ravnix/live".text = "RAVNIX live installation medium\n";
  # Generated hardware configuration replaces this on the installed system.
  system.nixos.variant_id = "live";
}
