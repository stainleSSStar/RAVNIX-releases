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
  imports = [
    "${modulesPath}/installer/cd-dvd/iso-image.nix"
    # Bundle the NixOS/Nixpkgs channel so the standard graphical installer,
    # which writes a channel-style configuration, can install offline.
    "${modulesPath}/installer/cd-dvd/channel.nix"
  ];
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
    # RAVNIX branded bootloaders: legacy BIOS (isolinux) and UEFI (GRUB).
    splashImage = ../assets/ravnix-boot-bios.png;
    efiSplashImage = ../assets/ravnix-boot-efi.png;
  };
  boot.kernelParams = [ "console=tty0" "console=ttyS0,115200n8" ];
  boot.loader.grub.memtest86.enable = false;
  users.users.ravnix = {
    isNormalUser = true;
    extraGroups = [
      "wheel"
      "networkmanager"
      "video"
      "render"
      "input"
      "lp"
      "scanner"
      "dialout"
    ];
    initialHashedPassword = "";
  };
  services.getty.autologinUser = "ravnix";
  services.getty.helpLine = "RAVNIX LIVE: desktop auto-login | sudo ravnix-install | ravnix-guide";
  # The live medium goes straight into the desktop; an installed system asks
  # for a password instead.
  services.displayManager.autoLogin = {
    enable = true;
    user = "ravnix";
  };
  security.sudo.wheelNeedsPassword = lib.mkForce false;
  # The graphical installer runs privileged actions through pkexec. On the
  # live medium the wheel group is trusted without a password, exactly like
  # the upstream NixOS graphical installation CD.
  security.polkit.extraConfig = ''
    polkit.addRule(function(action, subject) {
      if (subject.isInGroup("wheel")) {
        return polkit.Result.YES;
      }
    });
  '';
  system.tools = {
    nixos-enter.enable = true;
    nixos-generate-config.enable = true;
    nixos-install.enable = true;
  };
  environment.systemPackages = [ installer guide ];
  # The installation builds the initial ramdisk and installs the bootloader
  # inside the guest, so the live image has to carry everything the installed
  # system needs. Without these paths the installation depends on the binary
  # cache, and one broken connection to it aborts an installation that has
  # already erased the disk. Both GRUB variants are included because the
  # installer writes a BIOS configuration for one boot mode and an EFI
  # configuration for the other. The initial ramdisk is built with the
  # compiler-less standard environment and the ramdisk tool, exactly like the
  # upstream installation device carries them.
  system.extraDependencies = [
    pkgs.grub2
    (pkgs.grub2.override { efiSupport = true; })
    pkgs.efibootmgr
    pkgs.makeInitrdNGTool
    pkgs.stdenvNoCC
    pkgs.busybox
    pkgs.jq
  ];
  environment.etc."ravnix/source".source = source;
  environment.etc."ravnix/live".text = "RAVNIX live installation medium\n";
  # Generated hardware configuration replaces this on the installed system.
  system.nixos.variant_id = "live";
  # Desktop shortcuts for both installers.
  system.activationScripts.ravnixDesktop = ''
    desktop=/home/ravnix/Desktop
    mkdir -p "$desktop"
    chown ravnix /home/ravnix "$desktop"
    ln -sfT ${pkgs.calamares-nixos}/share/applications/calamares.desktop \
      "$desktop/install-nixos-graphical.desktop"
    ln -sfT ${pkgs.kdePackages.konsole}/share/applications/org.kde.konsole.desktop \
      "$desktop/ravnix-guide.desktop"
    cat > "$desktop/install-ravnix.desktop" <<EOF
    [Desktop Entry]
    Type=Application
    Name=Install RAVNIX
    Comment=Install RAVNIX with its own text installer
    Exec=${pkgs.kdePackages.konsole}/bin/konsole --hold -e sudo ${installer}/bin/ravnix-install
    Icon=drive-harddisk
    Terminal=false
    Categories=System;
    EOF
    cat > "$desktop/ravnix-guide.desktop" <<EOF
    [Desktop Entry]
    Type=Application
    Name=RAVNIX Guide
    Comment=Read the live and installation guide
    Exec=${pkgs.kdePackages.konsole}/bin/konsole --hold -e ${guide}/bin/ravnix-guide
    Icon=help-browser
    Terminal=false
    Categories=System;
    EOF
    chown -R ravnix "$desktop"
  '';
}
