{
  description = "RAVNIX — minimal NixOS console live/installer distribution";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/26f4107e47e3ad0ffd0db220469ba83b6f6d96e8";
  outputs = { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};
      mkSystem = modules: nixpkgs.lib.nixosSystem {
        inherit system;
        modules = [ ./modules/base.nix ] ++ modules;
      };
      live = mkSystem [ ./modules/live.nix ];
      probe = mode: mkSystem [{
        boot.loader.grub = {
          enable = true;
          device = if mode == "uefi" then "nodev" else "/dev/sda";
          efiSupport = mode == "uefi";
          efiInstallAsRemovable = mode == "uefi";
        };
        boot.loader.efi.canTouchEfiVariables = false;
        fileSystems = {
          "/" = { device = "/dev/disk/by-label/RAVNIX"; fsType = "ext4"; };
        } // nixpkgs.lib.optionalAttrs (mode == "uefi") {
          "/boot/efi" = { device = "/dev/disk/by-label/EFI"; fsType = "vfat"; };
        };
      }];
    in {
      nixosModules.default = import ./modules/base.nix;
      nixosConfigurations = { inherit live; } // nixpkgs.lib.optionalAttrs
        (builtins.pathExists ./host.nix && builtins.pathExists ./hardware-configuration.nix) {
          ravnix = mkSystem [ ./host.nix ./hardware-configuration.nix ];
        };
      packages.${system} = {
        iso = live.config.system.build.isoImage;
        default = self.packages.${system}.iso;
      };
      checks.${system} = {
        bios = (probe "bios").config.system.build.toplevel;
        uefi = (probe "uefi").config.system.build.toplevel;
      };
      formatter.${system} = pkgs.nixfmt;
    };
}
