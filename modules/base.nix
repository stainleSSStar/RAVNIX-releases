{ lib, pkgs, modulesPath, nixpkgsSource, ... }:
{
  imports = [ "${modulesPath}/profiles/minimal.nix" ./desktop.nix ];
  system.stateVersion = "26.05";
  system.nixos = {
    distroId = "ravnix";
    distroName = "RAVNIX";
    extraOSReleaseArgs.ID_LIKE = "nixos";
  };
  networking.hostName = lib.mkDefault "ravnix";
  networking.networkmanager.enable = true;
  networking.modemmanager.enable = false;
  networking.firewall.enable = true;
  services.openssh.enable = false;
  services.timesyncd.enable = true;
  # Every firmware blob and every boot-time storage driver, so the same image
  # works in a virtual machine and on real hardware.
  hardware.enableAllHardware = true;
  hardware.cpu.intel.updateMicrocode = true;
  hardware.cpu.amd.updateMicrocode = true;
  time.timeZone = lib.mkDefault "Europe/Warsaw";
  i18n.defaultLocale = "en_US.UTF-8";
  i18n.supportedLocales = [ "en_US.UTF-8/UTF-8" "pl_PL.UTF-8/UTF-8" ];
  console.keyMap = "us";
  programs.fish = {
    enable = true;
    generateCompletions = false;
    interactiveShellInit = ''
      set -g fish_greeting
      set -g fish_color_normal a6f28a
      set -g fish_color_command a6f28a
      set -g fish_color_error fb7185
      set -g fish_color_comment b394c4
    '';
    promptInit = ''
      function fish_prompt
        set_color a6f28a
        printf '%s@%s %s > ' $USER (prompt_hostname) (prompt_pwd)
        set_color normal
      end
    '';
  };
  users.defaultUserShell = pkgs.fish;
  users.users.root.hashedPassword = "!";
  users.mutableUsers = true;
  security.sudo = { enable = true; wheelNeedsPassword = true; };
  # The desktop needs a policy agent for mounting disks and other actions
  # that ask for authorisation.
  security.polkit.enable = true;
  environment.defaultPackages = [ ];
  # Offline configuration editing and basic network/storage diagnosis on both
  # the live medium and the installed system.
  environment.systemPackages = with pkgs; [
    nano less curl pciutils usbutils ethtool smartmontools
  ];
  environment.variables.EDITOR = "nano";
  # Keep rebuild/rollback, but leave installation tools on the ISO only.
  system.tools = {
    nixos-build-vms.enable = false;
    nixos-enter.enable = lib.mkDefault false;
    nixos-generate-config.enable = lib.mkDefault false;
    nixos-install.enable = lib.mkDefault false;
    nixos-option.enable = false;
  };
  # The pinned Nixpkgs source belongs to the system itself, not only to the
  # live image. The configuration is read from the Nixpkgs source when the
  # system is evaluated, so a machine that carries the source can rebuild
  # itself without a network connection: the flake input is already in the
  # store and does not have to be fetched again. Without it, every rebuild on
  # the installed machine downloads the whole source tree first.
  system.extraDependencies = [ nixpkgsSource ];
  nix.settings.experimental-features = [ "nix-command" "flakes" ];
  nix.settings.auto-optimise-store = true;
  nix.settings.trusted-users = [ "root" ];
  # A flaky connection to the binary cache must not abort a rebuild: the
  # connection gets more time and a failed transfer is retried more often
  # than the default five times.
  nix.settings.connect-timeout = 30;
  nix.settings.stalled-download-timeout = 120;
  nix.settings.download-attempts = 10;
  # No automatic updates or garbage collection: retain rollback generations.
  nix.gc.automatic = false;
  system.autoUpgrade.enable = false;
  boot.loader.timeout = lib.mkDefault 5;
  # RAVNIX branded GRUB on every boot of the installed system.
  boot.loader.grub.splashImage = ../assets/ravnix-boot-efi.png;
  boot.loader.grub.splashMode = "stretch";
  boot.loader.grub.backgroundColor = "#1a1423";
  environment.etc."issue".text = ''
    RAVNIX — NixOS 26.05 with KDE Plasma 6

    Desktop: log in graphically      Shell: Fish
    Network: system tray or nmtui   Installer: desktop shortcut
  '';
}
