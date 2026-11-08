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

    def test_the_colour_scheme_is_in_the_profile_of_the_user_as_well(self):
        # The session of the desktop does not always carry the profile of the
        # system in its data directories, so the scheme has to be in the
        # profile of the user too.
        desktop = self.desktop()
        self.assertIn('skel/.local/share/color-schemes/RAVNIX-PurpleNeon.colors', desktop)

    def test_the_global_theme_of_the_desktop_exists(self):
        # The global theme is a package of the Plasma workspace. The one of
        # RAVNIX has to be shipped, otherwise the settings of the desktop only
        # offer the themes of KDE, and the user cannot change the theme at
        # all.
        desktop = self.desktop()
        self.assertIn('share/plasma/look-and-feel/org.kde.ravnix.purpleneon.desktop', desktop)
        metadata = ROOT / 'assets/ravnix-lookandfeel/metadata.json'
        self.assertTrue(metadata.is_file(), 'the global theme has no metadata')
        self.assertIn('org.kde.ravnix.purpleneon.desktop', metadata.read_text())

    def test_the_global_theme_sets_the_colours_of_the_distribution(self):
        # The global theme is what the desktop applies when the user picks it.
        # The colours of RAVNIX are the ones of the distribution, and the
        # Plasma theme stays the default one, because it takes the colours
        # of the scheme: that is how the panel of the desktop becomes dark.
        defaults = (ROOT / 'assets/ravnix-lookandfeel/contents/defaults').read_text()
        self.assertIn('ColorScheme=RAVNIX-PurpleNeon', defaults)
        self.assertIn('name=default', defaults)
        self.assertIn('Theme=breeze-dark', defaults)

    def test_the_configuration_of_the_desktop_names_the_theme_of_the_distribution(self):
        # The configuration of the desktop decides which colours and which
        # icons the session starts with. The theme of KDE was named there,
        # and it brought the standard colours with it.
        globals_file = (ROOT / 'assets/kdeglobals').read_text()
        self.assertIn('ColorScheme=RAVNIX-PurpleNeon', globals_file)
        self.assertIn('lookAndFeelPackage=org.kde.ravnix.purpleneon.desktop', globals_file)
        self.assertIn('Theme=breeze-dark', globals_file)

    def test_the_configuration_of_the_desktop_has_no_file_that_does_not_exist(self):
        # A line that names an update file which is not there makes the
        # desktop complain about its configuration on every login.
        globals_file = (ROOT / 'assets/kdeglobals').read_text()
        self.assertNotIn('update_info', globals_file)

    def test_the_colours_of_the_distribution_are_dark(self):
        # The panel of the desktop takes its colour from the background of
        # the scheme. A scheme with a light background gives a white panel,
        # which is what a user saw on RAVNIX.
        scheme = (ROOT / 'assets/RAVNIX-PurpleNeon.colorscheme').read_text()
        for group in ('Colors:Window', 'Colors:View'):
            block = scheme.split(f'[{group}]', 1)[1].split('\n[', 1)[0]
            match = re.search(r'^BackgroundNormal=(\d+),(\d+),(\d+)$', block, re.M)
            self.assertIsNotNone(match, f'{group} has no background')
            red, green, blue = (int(value) for value in match.groups())
            self.assertLess((red + green + blue) / 3, 100, f'{group} is not dark')

    def test_the_pointer_of_the_distribution_is_shipped(self):
        # The cursor theme is read from the file kcminputrc and from no other
        # one, so it needs its own file in the profile of the user.
        desktop = self.desktop()
        self.assertIn('skel/.config/kcminputrc', desktop)
        self.assertIn('cursorTheme=breeze_cursors', (ROOT / 'assets/kcminputrc').read_text())

    def test_the_wallpaper_is_applied_until_it_is_really_there(self):
        # The command that sets the wallpaper can be sent to the shell before
        # it is able to keep it, so the script has to keep trying and has to
        # check the configuration of the desktop.
        script = (ROOT / 'assets/ravnix-branding.sh').read_text()
        self.assertIn('plasma-apply-wallpaperimage', script)
        self.assertIn('ravnix-wallpaper.jpg', script)
        self.assertIn('plasma-org.kde.plasma.desktop-appletsrc', script)
        self.assertIn('while [ "$count" -lt "$attempts" ]', script)

    def test_the_wallpaper_waits_for_the_shell_of_the_desktop(self):
        # The shell writes the layout of the desktop when it starts, and it
        # throws away a wallpaper that was set before that. The wallpaper of
        # RAVNIX was therefore seen only a minute or two after the login.
        script = (ROOT / 'assets/ravnix-branding.sh').read_text()
        self.assertIn('shell_ready', script)
        wait = script.index('shell_ready && break')
        apply_wallpaper = script.index('plasma-apply-wallpaperimage "$wallpaper"')
        self.assertLess(wait, apply_wallpaper)

    def test_the_wallpaper_of_the_user_is_never_thrown_away(self):
        # A picture that the user chose stays. The script only sets the
        # wallpaper of RAVNIX when the desktop has no picture that works.
        script = (ROOT / 'assets/ravnix-branding.sh').read_text()
        self.assertIn('wallpaper_broken', script)
        self.assertIn('if wallpaper_broken; then', script)

    def test_the_colours_are_applied_once_and_not_against_the_user(self):
        # The user picks a theme in the settings of the desktop. A script that
        # puts the colours back every second would take that choice away
        # again, which is what a user complained about: the theme of the
        # desktop never changed. A marker remembers that the colours are
        # there.
        script = (ROOT / 'assets/ravnix-branding.sh').read_text()
        self.assertIn('branding-applied', script)
        self.assertIn('if [ ! -f "$marker" ]; then', script)
        self.assertIn('plasma-apply-colorscheme', script)
        self.assertIn('scheme_in_globals', script)

    def test_the_two_ways_to_start_the_script_do_not_work_at_the_same_time(self):
        # The service of the session and the entry in the autostart of the
        # desktop start the script at the same moment.
        script = (ROOT / 'assets/ravnix-branding.sh').read_text()
        self.assertIn('branding.lock', script)


class KdePackages(unittest.TestCase):
    def desktop(self):
        return (ROOT / 'modules/desktop.nix').read_text()

    def test_the_desktop_ships_the_packages_kde_needs(self):
        # A package that is missing shows up as a missing setting in the
        # desktop, and the user cannot repair that. The list of the packages
        # of KDE is therefore written down in the module and not left to the
        # defaults of nixpkgs.
        desktop = self.desktop()
        for package in (
            'plasma-workspace', 'plasma-desktop', 'systemsettings', 'kcmutils',
            'libplasma', 'kdeplasma-addons', 'breeze', 'breeze-icons',
            'breeze-gtk', 'kwallet', 'kwallet-pam', 'kwalletmanager',
            'polkit-kde-agent-1', 'kscreenlocker', 'kwin', 'kded', 'kio',
            'kio-extras', 'kio-admin', 'kglobalacceld', 'kactivitymanagerd',
            'konsole', 'dolphin', 'kate', 'spectacle', 'gwenview', 'ark',
            'elisa', 'okular', 'khelpcenter', 'kde-cli-tools', 'kmenuedit',
            'kinfocenter', 'plasma-systemmonitor', 'ksystemstats', 'milou',
            'baloo', 'knighttime', 'kunifiedpush', 'solid', 'drkonqi',
            'aurorae', 'qqc2-breeze-style', 'qqc2-desktop-style',
            'ocean-sound-theme', 'plasma-integration', 'kde-gtk-config',
        ):
            with self.subTest(package=package):
                self.assertRegex(desktop, rf'(?m)^\s+{re.escape(package)}$')

    def test_the_packages_of_kde_are_added_to_the_system(self):
        desktop = self.desktop()
        self.assertIn('environment.systemPackages', desktop)
        self.assertIn('++ kdeDesktop;', desktop)


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
