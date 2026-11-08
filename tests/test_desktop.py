"""Test the parts of the RAVNIX desktop that were found on real hardware.

Every test in here covers a defect that a user ran into on a real machine:
a wallet that stayed empty, a theme that never changed, a browser that was
told to skip its sandbox, a wallpaper that appeared minutes after the login
and a fastfetch that refused to start because of a colour it does not know.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]

# The colours fastfetch understands. Everything else is rejected with
# "invalid color code found", which is what a user saw on the RAVNIX logo.
FASTFETCH_COLOURS = {
    'black', 'red', 'green', 'yellow', 'blue', 'magenta', 'cyan', 'white',
    'bright_black', 'bright_red', 'bright_green', 'bright_yellow',
    'bright_blue', 'bright_magenta', 'bright_cyan', 'bright_white', 'default',
}


class DesktopBranding(unittest.TestCase):
    def desktop(self):
        return (ROOT / 'modules/desktop.nix').read_text()

    def test_the_colour_scheme_is_shipped_under_both_names(self):
        # KDE Frameworks 6.6 reads the colour schemes from the files that end
        # in ".colors"; the older name is ".colorscheme". The scheme of RAVNIX
        # has to be found by the desktop of this version, and the desktop of
        # the next one, so both names are shipped.
        desktop = self.desktop()
        self.assertIn('$out/share/color-schemes/RAVNIX-PurpleNeon.colors', desktop)
        self.assertIn('$out/share/color-schemes/RAVNIX-PurpleNeon.colorscheme', desktop)

    def test_the_global_theme_of_the_desktop_exists(self):
        # The look and feel package is part of the Plasma workspace. If it is
        # missing, the desktop falls back to the standard theme and the user
        # cannot change the theme at all.
        globals_file = (ROOT / 'assets/kdeglobals').read_text()
        self.assertIn('lookAndFeelPackage=org.kde.breezedark.desktop', globals_file)
        self.assertIn('ColorScheme=RAVNIX-PurpleNeon', globals_file)

    def test_the_wallpaper_is_applied_until_it_is_really_there(self):
        # A single attempt to apply the wallpaper comes too early, because the
        # Plasma shell is not up yet, and then the desktop keeps the default
        # wallpaper for the rest of the session. The script has to keep trying
        # and has to check the configuration of the desktop.
        script = (ROOT / 'assets/ravnix-branding.sh').read_text()
        self.assertIn('plasma-apply-wallpaperimage', script)
        self.assertIn('ravnix-wallpaper.jpg', script)
        self.assertIn('plasma-org.kde.plasma.desktop-appletsrc', script)
        self.assertIn('while [ "$count" -lt "$attempts" ]', script)

    def test_the_colours_are_applied_once_and_not_against_the_user(self):
        # The user picks a theme in the settings of the desktop. A script that
        # puts the colours back every second would take that choice away
        # again, so the colours are applied once, after the wallpaper is
        # there.
        script = (ROOT / 'assets/ravnix-branding.sh').read_text()
        wallpaper_loop = script.index('while [ "$count" -lt "$attempts" ]')
        colour_loop = script.index('while [ "$count" -lt 10 ]')
        self.assertLess(wallpaper_loop, colour_loop)
        # The colours are not applied inside the loop of the wallpaper.
        wallpaper_loop_body = script[wallpaper_loop:colour_loop]
        self.assertNotIn('apply_scheme', wallpaper_loop_body)


class Wallet(unittest.TestCase):
    def test_the_wallet_daemon_starts_with_the_session(self):
        # The wallet keeps the secrets of the session, the password of the
        # wireless network among them. The daemon is started by the D-Bus when
        # an application asks for it, but a session that never asks stays
        # without a wallet, so the daemon starts with the session.
        desktop = (ROOT / 'modules/desktop.nix').read_text()
        self.assertIn('systemd.user.services.kwalletd6', desktop)
        self.assertIn('${kde.kwallet}/bin/kwalletd6', desktop)
        self.assertIn('graphical-session.target', desktop)

    def test_the_wallet_service_does_not_fail_when_the_daemon_is_already_there(self):
        # The D-Bus starts the daemon at the login, when the module of the
        # password of the account asks for the wallet. A second instance
        # cannot take the name of the bus and would leave a failed unit, and
        # the service has to notice that the daemon is running already.
        desktop = (ROOT / 'modules/desktop.nix').read_text()
        self.assertIn('org.kde.kwalletd6', desktop)
        self.assertIn('|| exit 0', desktop)
        self.assertIn('Restart = "no"', desktop)

    def test_the_power_profiles_of_the_machine_are_available(self):
        # Plasma asks the daemon of the power profiles over the D-Bus. Without
        # that daemon the desktop says that the power profiles are not
        # supported on this machine.
        desktop = (ROOT / 'modules/desktop.nix').read_text()
        self.assertIn('services.power-profiles-daemon.enable = true;', desktop)

    def test_the_network_applet_of_the_desktop_is_there(self):
        # The applet of the network is the one that puts the password of the
        # wireless network into the wallet. Nixpkgs adds it when the network
        # manager is enabled, so the configuration has to keep that manager.
        base = (ROOT / 'modules/base.nix').read_text()
        self.assertIn('networking.networkmanager.enable', base)


class Browser(unittest.TestCase):
    def brave(self):
        return (ROOT / 'pkgs/brave-origin.nix').read_text()

    def test_the_browser_is_not_told_to_skip_its_sandbox(self):
        # The flag "--disable-setuid-sandbox" switches the sandbox of the
        # browser off. The Nix store cannot hold the setuid helper of the
        # sandbox, so the browser uses the sandbox of the user namespace
        # instead, which needs the user namespaces to be allowed.
        brave = self.brave()
        self.assertNotIn('--disable-setuid-sandbox', brave)
        desktop = (ROOT / 'modules/desktop.nix').read_text()
        self.assertIn('security.allowUserNamespaces = true;', desktop)

    def test_the_broken_setuid_helper_is_not_shipped(self):
        # A helper that is there but not setuid makes the browser refuse to
        # start, so it is not shipped at all.
        brave = self.brave()
        self.assertIn('rm -f "$out/opt/brave.com/brave-origin/chrome-sandbox"', brave)


class Fastfetch(unittest.TestCase):
    def colours(self):
        # The configuration is JSON with comments, and the address of the
        # schema holds a "//", so the colours are read out of it directly
        # instead of parsing the whole file.
        configuration = (ROOT / 'assets/fastfetch.jsonc').read_text()
        block = re.search(r'"color"\s*:\s*\{(.*?)\}', configuration, re.S)
        self.assertIsNotNone(block, 'the logo of the configuration has no colours')
        return dict(re.findall(r'"(\d+)"\s*:\s*"([^"]+)"', block.group(1)))

    def test_the_logo_uses_colours_that_fastfetch_knows(self):
        colours = self.colours()
        self.assertTrue(colours)
        for position, colour in colours.items():
            with self.subTest(position=position, colour=colour):
                if colour.startswith('#'):
                    self.assertRegex(colour, r'^#[0-9a-fA-F]{6}$')
                    continue
                self.assertIn(colour, FASTFETCH_COLOURS)

    def test_the_logo_uses_the_colours_of_the_distribution(self):
        # The logo of the distribution is purple and pink, the colours of the
        # colour scheme of RAVNIX.
        colours = set(self.colours().values())
        self.assertIn('#a78bfa', colours)
        self.assertIn('#f472b6', colours)


if __name__ == '__main__':
    unittest.main()
