#!/usr/bin/env python3
"""Fast source checks; Nix evaluation and real VM boots run separately in CI."""
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
for source in (ROOT / 'scripts').glob('*.sh'):
    subprocess.run(['bash', '-n', str(source)], check=True)
for source in (ROOT / 'scripts').glob('*.py'):
    compile(source.read_text(), str(source), 'exec')
base = (ROOT / 'modules/base.nix').read_text()
desktop = (ROOT / 'modules/desktop.nix').read_text()
live = (ROOT / 'modules/live.nix').read_text()
flake = (ROOT / 'flake.nix').read_text()

# Core distro guarantees.
assert 'services.openssh.enable = false;' in base
assert 'wheelNeedsPassword = true;' in base
assert 'users.users.root.hashedPassword = "!";' in base
assert 'programs.fish' in base and 'networkmanager.enable = true;' in base
assert 'users.defaultUserShell = pkgs.fish;' in base
assert 'hardware.enableAllHardware = true;' in base
assert 'live.nix' not in base and 'ravnix-install' not in base
assert 'nixos-unstable' not in flake
# The distro is a desktop one now: the console-only guards are gone for good.
assert 'services.xserver.enable = false;' not in base

# Desktop layer.
assert 'services.desktopManager.plasma6.enable = true;' in desktop
assert 'services.xserver.enable = true;' in desktop
assert 'services.displayManager.sddm.enable = true;' in desktop
assert 'services.displayManager.sddm.theme' in desktop
assert 'services.pipewire.enable = true;' in desktop
assert 'xdg.autostart.enable = true;' in desktop
assert 'xdg.icons.enable = true;' in desktop
assert 'xdg.mime.enable = true;' in desktop
assert 'hardware.graphics.enable32Bit = true;' in desktop
assert 'hardware.graphics.extraPackages' in desktop
assert 'hardware.bluetooth.enable = true;' in desktop
assert 'programs.partition-manager.enable = true;' in desktop
for package in ('mc', 'btop', 'fastfetch', 'calamares-nixos', 'braveOrigin'):
    assert package in desktop, package
assert '../pkgs/brave-origin.nix' in desktop
# NixOS never copies /etc/skel into a new home directory, so the profile has
# to be seeded into the accounts by the system itself.
assert 'users-ravnix-profile' in desktop
assert 'cp -rn /etc/skel' in desktop

# Live medium: autologin into the desktop, branded bootloaders.
assert 'services.displayManager.autoLogin' in live
assert 'services.getty.autologinUser = "ravnix";' in live
assert 'ravnix-boot-bios.png' in live and 'ravnix-boot-efi.png' in live

# Branding assets must exist.
for asset in ('RAVNIX-PurpleNeon.colorscheme', 'ravnix-wallpaper.jpg', 'fastfetch-logo.txt',
              'btop-ravnix.theme', 'kdeglobals', 'konsolerc', 'RAVNIX.profile',
              'ravnix-boot-efi.png', 'ravnix-boot-bios.png'):
    assert (ROOT / 'assets' / asset).is_file(), asset
for asset in ('Main.qml', 'metadata.desktop', 'theme.conf', 'background.jpg', 'angle-down.png'):
    assert (ROOT / 'assets' / 'sddm-ravnix' / asset).is_file(), asset
assert (ROOT / 'pkgs' / 'brave-origin.nix').is_file()

# The wallpaper has to fill a 1920x1080 display.
def jpeg_size(data):
    offset = 2
    while offset < len(data):
        if data[offset] != 0xFF:
            offset += 1
            continue
        marker = data[offset + 1]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            height = int.from_bytes(data[offset + 5:offset + 7], 'big')
            width = int.from_bytes(data[offset + 7:offset + 9], 'big')
            return width, height
        length = int.from_bytes(data[offset + 2:offset + 4], 'big')
        offset += 2 + length
    raise AssertionError('no JPEG frame header found')

width, height = jpeg_size((ROOT / 'assets' / 'ravnix-wallpaper.jpg').read_bytes())
assert width >= 1920 and height >= 1080, (width, height)
assert (ROOT / 'assets' / 'sddm-ravnix' / 'background.jpg').is_file()

print('RAVNIX source checks passed')
