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
