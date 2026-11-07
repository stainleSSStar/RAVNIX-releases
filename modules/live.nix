{ config, lib, pkgs, modulesPath, nixpkgsSource, ... }:
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
  # The graphical installer installs RAVNIX instead of plain NixOS. The stock
  # Calamares module writes a configuration of its own and installs stock
  # NixOS, so a machine installed with it carries none of the RAVNIX branding.
  # Our own module runs the RAVNIX installer instead, which makes the
  # graphical and the text installer produce the same system.
  #
  # Calamares looks for modules in the directories of "modules-search" and
  # uses the first module it finds for a name, so the directory of our module
  # is put in front of the one of the NixOS extensions.
  calamaresModules = pkgs.runCommand "ravnix-calamares-modules" { } ''
    mkdir -p $out/lib/calamares/modules/nixos
    cp ${./calamares/nixos/module.desc} $out/lib/calamares/modules/nixos/module.desc
    substitute ${./calamares/nixos/main.py} $out/lib/calamares/modules/nixos/main.py \
      --replace-fail @ravnixInstaller@ ${installer}/bin/ravnix-install
  '';
  # The wizard shows the branding of RAVNIX instead of the one of NixOS.
  calamaresBranding = pkgs.linkFarm "ravnix-calamares-branding" [
    "share/calamares/branding/ravnix/branding.desc" ../modules/calamares/branding/ravnix/branding.desc
    "share/calamares/branding/ravnix/show.qml" ../modules/calamares/branding/ravnix/show.qml
    "share/calamares/branding/ravnix/ravnix-logo.png" ../assets/calamares/ravnix-logo.png
    "share/calamares/branding/ravnix/ravnix-welcome.png" ../assets/calamares/ravnix-welcome.png
    "share/calamares/branding/ravnix/ravnix-background.jpg" ../assets/calamares/ravnix-background.jpg
  ];
  calamaresExtensions = pkgs.calamares-nixos-extensions.overrideAttrs (old: {
    postInstall = (old.postInstall or "") + ''
      substituteInPlace $out/etc/calamares/settings.conf \
        --replace-fail "modules-search: [ local, $out/lib/calamares/modules ]" \
        "modules-search: [ local, ${calamaresModules}/lib/calamares/modules, $out/lib/calamares/modules ]" \
        --replace-fail "branding: nixos" "branding: ravnix" \
        --replace-fail "  - packagechooser" "" \
        --replace-fail "  - notesqml@unfree" ""
      # The partitioning of the graphical installer has to produce the layout
      # the RAVNIX configuration expects: the EFI system partition at /boot/efi
      # and a partition for the BIOS bootloader on a GPT disk. The stock
      # configuration mounts the EFI system partition at /boot and offers
      # encryption and LVM, which the RAVNIX configuration cannot use.
      cp ${./calamares/config/partition.conf} $out/etc/calamares/modules/partition.conf
      # The installed system needs the same space as the text installer asks
      # for, so the graphical installer refuses a smaller disk right away.
      sed -i -E 's/^[[:space:]]*requiredStorage:.*$/requiredStorage: 16/' \
        $out/etc/calamares/modules/welcome.conf
      # The RAVNIX policy keeps the root account locked: the account of the
      # administrator is the only one with a password, and it needs one for
      # sudo. Without this the graphical installer would ask for a root
      # password and unlock the root account.
      sed -i -E 's/^[[:space:]]*setRootPassword:.*$/setRootPassword: false/' \
        $out/etc/calamares/modules/users.conf
    '';
  });
  calamares = pkgs.calamares-nixos.override {
    calamares-nixos-extensions = calamaresExtensions;
    extraWrapperArgs = [
      "--prefix XDG_DATA_DIRS : ${calamaresBranding}/share"
      "--prefix XDG_DATA_DIRS : ${calamaresExtensions}/share"
      "--prefix XDG_CONFIG_DIRS : ${calamaresExtensions}/etc"
      "--add-flag --xdg-config"
    ];
  };
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
  environment.systemPackages = [ installer guide calamares ];
  # The installation builds the initial ramdisk and installs the bootloader
  # inside the guest, so the live image has to carry everything the installed
  # system needs. Without these paths the installation depends on the binary
  # cache, and one broken connection to it aborts an installation that has
  # already erased the disk. Both GRUB variants are included because the
  # installer writes a BIOS configuration for one boot mode and an EFI
  # configuration for the other. The initial ramdisk is built with the
  # compiler-less standard environment and the ramdisk tool, exactly like the
  # upstream installation device carries them.
  #
  # GRUB is installed with a Perl script that reads the device map, so the
  # live image carries the same Perl environment that the installed system
  # will use. Without it the installation would have to fetch compiled Perl
  # modules, which needs a compiler and therefore a network connection.
  #
  # The pinned Nixpkgs source belongs to the live image as well. The base
  # module puts it into every system, so the installation evaluates the
  # configuration from the copied source tree without downloading it first.
  system.extraDependencies = [
    pkgs.grub2
    (pkgs.grub2.override { efiSupport = true; })
    pkgs.efibootmgr
    pkgs.makeInitrdNGTool
    pkgs.stdenvNoCC
    pkgs.busybox
    pkgs.jq
    (pkgs.perl.withPackages (p: with p; [
      FileSlurp
      FileCopyRecursive
      XMLLibXML
      XMLSAX
      XMLSAXBase
      ListCompare
      JSON
    ]))
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
    ln -sfT ${pkgs.kdePackages.konsole}/share/applications/org.kde.konsole.desktop \
      "$desktop/ravnix-guide.desktop"
    cat > "$desktop/install-ravnix-graphical.desktop" <<EOF
    [Desktop Entry]
    Type=Application
    Name=Install RAVNIX graphically
    Comment=Install RAVNIX with the graphical installer
    Exec=${calamares}/bin/calamares
    Icon=drive-harddisk
    Terminal=false
    Categories=System;
    EOF
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
