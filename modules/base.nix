{ lib, pkgs, modulesPath, ... }:
{
  imports = [ "${modulesPath}/profiles/minimal.nix" ];
  system.stateVersion = "26.05";
  system.nixos = {
    distroId = "ravnix";
    distroName = "RAVNIX";
    extraOSReleaseArgs.ID_LIKE = "nixos";
  };
  networking.hostName = lib.mkDefault "ravnix";
  networking.networkmanager.enable = true;
  networking.networkmanager.plugins = lib.mkForce [ ];
  networking.modemmanager.enable = false;
  networking.firewall.enable = true;
  services.openssh.enable = false;
  services.xserver.enable = false;
  services.timesyncd.enable = true;
  hardware.enableRedistributableFirmware = true;
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
  environment.defaultPackages = [ ];
  # Offline configuration editing and basic network/storage diagnosis on both
  # the live medium and installed system; no desktop dependencies.
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
  nix.settings.experimental-features = [ "nix-command" "flakes" ];
  nix.settings.auto-optimise-store = true;
  nix.settings.trusted-users = [ "root" ];
  # No automatic updates or garbage collection: retain rollback generations.
  nix.gc.automatic = false;
  system.autoUpgrade.enable = false;
  boot.loader.timeout = lib.mkDefault 5;
  environment.etc."issue".text = ''
    RAVNIX — minimal NixOS console system
    Network: nmtui / nmcli    Shell: Fish
  '';
}
