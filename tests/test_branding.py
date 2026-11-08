"""The behaviour of the branding script of RAVNIX.

The script decides what the desktop of a new account looks like, and it was
the piece that was wrong: it set the wallpaper before the Plasma shell had
written the layout of the desktop, and it put the colours back every time the
session started. Both were found on real hardware.

The script is run here with stand-ins for the tools of the desktop, so the
order of its steps and its decisions can be watched. The stand-in for the
wallpaper refuses to do anything while the shell of the desktop has not
written the layout, which is what the shell does in reality: it throws a
wallpaper away that was set too early.
"""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'assets/ravnix-branding.sh'

# The shell writes the entries of a group either on lines of their own or
# behind the name of the group, and the entries of a group are separated by
# commas. Both ways are used here.
LAYOUT_COMPACT = (
    'wallpaperplugin=org.kde.image\n'
    '[Containments][1][Wallpaper][org.kde.image][General] Image=%s,FillMode=2\n'
)
LAYOUT_ON_OWN_LINES = (
    'wallpaperplugin=org.kde.image\n'
    '[Containments][1][Wallpaper][org.kde.image][General]\n'
    'Image=%s\n'
    'FillMode=2\n'
)

FAKE_TOOLS = {
    'plasma-apply-wallpaperimage': '''#!/bin/sh
config="${XDG_CONFIG_HOME:-$HOME/.config}/plasma-org.kde.plasma.desktop-appletsrc"
# The shell of the desktop is not up yet: it throws the wallpaper away.
[ -f "$config" ] || exit 1
printf 'wallpaperplugin=org.kde.image\\n[Containments][1][Wallpaper][org.kde.image][General] Image=file://%s,FillMode=2\\n' "$1" > "$config"
''',
    'plasma-apply-colorscheme': '''#!/bin/sh
config="${XDG_CONFIG_HOME:-$HOME/.config}/kdeglobals"
mkdir -p "$(dirname "$config")"
printf '[General]\\nColorScheme=%s\\n' "$1" > "$config"
''',
}


class BrandingScript(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self.home = self.tmp / 'home'
        self.home.mkdir()
        self.bin = self.tmp / 'bin'
        self.bin.mkdir()
        for name, body in FAKE_TOOLS.items():
            path = self.bin / name
            path.write_text(body)
            path.chmod(0o755)

        # The profile of the system: the wallpaper and the colour scheme.
        self.data = self.tmp / 'share'
        (self.data / 'backgrounds' / 'ravnix').mkdir(parents=True)
        (self.data / 'backgrounds' / 'ravnix' / 'ravnix-wallpaper.jpg').write_text('jpg')
        (self.data / 'color-schemes').mkdir(parents=True)
        (self.data / 'color-schemes' / 'RAVNIX-PurpleNeon.colors').write_text('[General]\n')

    def run_script(self):
        environment = dict(os.environ)
        environment.update({
            'HOME': str(self.home),
            'XDG_CONFIG_HOME': str(self.home / '.config'),
            'XDG_DATA_DIRS': str(self.data),
            'PATH': str(self.bin) + ':/usr/bin:/bin:/usr/sbin:/sbin',
        })
        for name in ('XDG_RUNTIME_DIR', 'DISPLAY', 'WAYLAND_DISPLAY'):
            environment.pop(name, None)
        result = subprocess.run(['sh', str(SCRIPT)], capture_output=True, text=True,
                                env=environment, timeout=300)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def config(self, name):
        return self.home / '.config' / name

    def applets(self):
        return self.config('plasma-org.kde.plasma.desktop-appletsrc').read_text()

    def globals(self):
        return self.config('kdeglobals').read_text()

    def shell_writes_the_layout(self, delay=0):
        # The shell of the desktop writes the layout of the desktop when it
        # starts. The wallpaper may only be set after that.
        def write():
            time.sleep(delay)
            path = self.config('plasma-org.kde.plasma.desktop-appletsrc')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('wallpaperplugin=org.kde.image\n')
        if delay:
            thread = threading.Thread(target=write)
            thread.start()
            self.addCleanup(thread.join)
            return thread
        write()
        return None

    def test_the_wallpaper_and_the_colours_are_applied(self):
        self.shell_writes_the_layout()
        self.run_script()
        self.assertIn('ravnix-wallpaper.jpg', self.applets())
        self.assertIn('ColorScheme=RAVNIX-PurpleNeon', self.globals())

    def test_the_script_waits_for_the_shell_of_the_desktop(self):
        # The shell comes up while the script is waiting. The wallpaper is
        # applied then, and not before: the stand-in for the tool refuses to
        # do anything while the layout of the desktop is missing.
        self.shell_writes_the_layout(delay=3)
        self.run_script()
        self.assertIn('ravnix-wallpaper.jpg', self.applets())

    def test_the_colours_are_applied_only_once(self):
        self.shell_writes_the_layout()
        self.run_script()
        # The user picks another theme in the settings of the desktop.
        self.config('kdeglobals').write_text('[General]\nColorScheme=BreezeDark\n')
        self.run_script()
        self.assertIn('ColorScheme=BreezeDark', self.globals())

    def test_the_picture_of_the_user_is_not_thrown_away(self):
        for layout in (LAYOUT_COMPACT, LAYOUT_ON_OWN_LINES):
            with self.subTest(layout=layout):
                self.shell_writes_the_layout()
                self.run_script()
                # The user picks a picture of their own.
                own = self.tmp / 'own.jpg'
                own.write_text('jpg')
                self.config('plasma-org.kde.plasma.desktop-appletsrc').write_text(
                    layout % f'file://{own}')
                self.run_script()
                self.assertIn(str(own), self.applets())
                self.assertNotIn('ravnix-wallpaper.jpg', self.applets())

    def test_a_wallpaper_that_is_gone_is_replaced(self):
        # A global theme of KDE asks for a wallpaper that is not installed.
        self.shell_writes_the_layout()
        self.run_script()
        self.config('plasma-org.kde.plasma.desktop-appletsrc').write_text(
            LAYOUT_COMPACT % 'Next')
        self.run_script()
        self.assertIn('ravnix-wallpaper.jpg', self.applets())


if __name__ == '__main__':
    unittest.main()
