# RAVNIX desktop layer — KDE Plasma 6, the Purple Neon theme, the custom
# wallpaper and the everyday applications.
#
# base.nix imports this module, so the live medium and the system installed
# from it get exactly the same desktop. Nothing here is specific to the ISO.
{ config, lib, pkgs, ... }:
let
  kde = pkgs.kdePackages;

  # Brave Origin is the standalone, feature-stripped Brave build that is free
  # on Linux. It is not in nixpkgs, so RAVNIX repackages it.
  braveOrigin = pkgs.callPackage ../pkgs/brave-origin.nix { };

  # Wallpaper, colour schemes, greeter theme and the fastfetch logo ship as
  # one package so they always land in the system profile together.
  branding = pkgs.runCommand "ravnix-branding" { } ''
    mkdir -p $out/share/backgrounds/ravnix
    mkdir -p $out/share/color-schemes
    mkdir -p $out/share/konsole
    mkdir -p $out/share/ravnix
    mkdir -p $out/share/sddm/themes/ravnix
    cp ${../assets/ravnix-wallpaper.jpg} $out/share/backgrounds/ravnix/ravnix-wallpaper.jpg
    cp ${../assets/RAVNIX-PurpleNeon.colorscheme} $out/share/color-schemes/RAVNIX-PurpleNeon.colorscheme
    cp ${../assets/RAVNIX.colorscheme} $out/share/konsole/RAVNIX.colorscheme
    cp ${../assets/fastfetch-logo.txt} $out/share/ravnix/fastfetch-logo.txt
    cp ${../assets/sddm-ravnix/Main.qml} $out/share/sddm/themes/ravnix/Main.qml
    cp ${../assets/sddm-ravnix/metadata.desktop} $out/share/sddm/themes/ravnix/metadata.desktop
    cp ${../assets/sddm-ravnix/theme.conf} $out/share/sddm/themes/ravnix/theme.conf
    cp ${../assets/sddm-ravnix/angle-down.png} $out/share/sddm/themes/ravnix/angle-down.png
    cp ${../assets/sddm-ravnix/background.jpg} $out/share/sddm/themes/ravnix/background.jpg
  '';

  brandingScript = pkgs.writeShellScriptBin "ravnix-branding" (builtins.readFile ../assets/ravnix-branding.sh);
in
{
  # --- Plasma 6 ------------------------------------------------------------
  services.desktopManager.plasma6.enable = true;
  services.xserver.enable = true;

  # The stock wallpapers add over 100 MiB to the closure; RAVNIX ships its
  # own wallpaper instead.
  environment.plasma6.excludePackages = [ kde.plasma-workspace-wallpapers ];

  # The greeter uses the RAVNIX theme, so the wallpaper and the purple
  # appearance are already there before anyone logs in.
  services.displayManager.sddm.enable = true;
  services.displayManager.sddm.wayland.enable = true;
  services.displayManager.sddm.theme = "${branding}/share/sddm/themes/ravnix";
  services.displayManager.defaultSession = "plasma";

  # kpmcore, the partition library the graphical installer relies on.
  programs.partition-manager.enable = true;

  # The minimal profile switches desktop integration off. A desktop needs
  # desktop icons, MIME associations, the portal and sound themes.
  xdg.autostart.enable = true;
  xdg.icons.enable = true;
  xdg.mime.enable = true;
  xdg.sounds.enable = true;
  xdg.portal.enable = true;

  # --- Sound ---------------------------------------------------------------
  # PipeWire as the sound server, with the ALSA and PulseAudio compatibility
  # layers so ordinary applications keep working.
  services.pipewire.enable = true;
  services.pipewire.audio.enable = true;
  services.pipewire.alsa.enable = true;
  services.pipewire.pulse.enable = true;

  # --- Power, printing, firmware ------------------------------------------
  powerManagement.enable = true;
  services.printing.enable = true;
  services.fwupd.enable = true;

  # --- Graphics and hardware ----------------------------------------------
  # Everything a VM or a real machine may need: 32-bit GL for legacy
  # applications, VA-API for hardware video, Bluetooth for peripherals.
  hardware.graphics.enable = true;
  hardware.graphics.enable32Bit = true;
  # VA-API drivers: Intel media engine and the VDPAU bridge for NVIDIA.
  # AMD and other GPUs get their VA driver from Mesa itself.
  hardware.graphics.extraPackages = with pkgs; [
    intel-media-driver
    libvdpau-va-gl
  ];
  hardware.bluetooth.enable = true;

  # --- Applications --------------------------------------------------------
  environment.systemPackages = with pkgs; [
    mc
    btop
    fastfetch
    xdg-utils
    mesa
    libva-utils
    kde.xdg-desktop-portal-kde
    kde.plasma-disks
    # The standard NixOS graphical installer, next to RAVNIX's own installer.
    calamares-nixos
    calamares-nixos-extensions
    gparted
    braveOrigin
    branding
  ];

  # --- Branding ------------------------------------------------------------
  # Brave Origin handles web content by default.
  xdg.mime.defaultApplications = {
    "text/html" = [ "brave-origin.desktop" ];
    "application/xhtml+xml" = [ "brave-origin.desktop" ];
    "application/xml" = [ "brave-origin.desktop" ];
    "x-scheme-handler/http" = [ "brave-origin.desktop" ];
    "x-scheme-handler/https" = [ "brave-origin.desktop" ];
  };

  # --- User configuration --------------------------------------------------
  # Skel files are copied into every new home directory, so the theme, the
  # console profile and the tool configuration are in place on first login.
  environment.etc."skel/.config/kdeglobals".source = ../assets/kdeglobals;
  environment.etc."skel/.config/konsolerc".source = ../assets/konsolerc;
  environment.etc."skel/.local/share/konsole/RAVNIX.profile".source = ../assets/RAVNIX.profile;
  # The colour schemes also live in the user profile, where KDE always looks
  # for them, whatever the session data directories happen to be.
  environment.etc."skel/.local/share/color-schemes/RAVNIX-PurpleNeon.colorscheme".source = ../assets/RAVNIX-PurpleNeon.colorscheme;
  environment.etc."skel/.local/share/konsole/RAVNIX.colorscheme".source = ../assets/RAVNIX.colorscheme;
  environment.etc."skel/.config/fastfetch/config.jsonc".source = ../assets/fastfetch.jsonc;
  environment.etc."skel/.config/btop/btop.conf".source = ../assets/btop.conf;
  environment.etc."skel/.config/btop/themes/ravnix.theme".source = ../assets/btop-ravnix.theme;
  # Root gets the same fastfetch branding.
  environment.etc."root/.config/fastfetch/config.jsonc".source = ../assets/fastfetch.jsonc;

  # --- Applying the theme --------------------------------------------------
  # The wallpaper and the colour scheme are applied once the Plasma shell is
  # up. Two independent triggers keep this working regardless of how the
  # session was started; the script is idempotent.
  systemd.user.services.ravnix-branding = {
    description = "Apply the RAVNIX Purple Neon theme and wallpaper";
    wantedBy = [ "graphical-session.target" ];
    serviceConfig = {
      Type = "oneshot";
      ExecStart = "${brandingScript}/bin/ravnix-branding";
    };
  };

  environment.etc."xdg/autostart/ravnix-branding.desktop".text = ''
    [Desktop Entry]
    Type=Application
    Name=RAVNIX Branding
    Comment=Apply the RAVNIX Purple Neon theme and wallpaper
    Exec=${brandingScript}/bin/ravnix-branding
    Terminal=false
    NoDisplay=true
    X-KDE-autostart-phase=Application
  '';
}
