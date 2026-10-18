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
assert 'services.xserver.enable = false;' in base
assert 'services.openssh.enable = false;' in base
assert 'wheelNeedsPassword = true;' in base
assert 'users.users.root.hashedPassword = "!";' in base
assert 'programs.fish' in base and 'networkmanager.enable = true;' in base
assert not re.search(r'pkgs\.(?:xfce|xorg|gnome|plasma|pipewire)', base)
assert 'live.nix' not in base and 'ravnix-install' not in base
assert 'nixos-unstable' not in (ROOT / 'flake.nix').read_text()
print('RAVNIX source checks passed')
