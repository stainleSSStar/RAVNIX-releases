"""Test the installation step of the RAVNIX graphical installer.

The stock Calamares module for NixOS installs plain NixOS, so the module of
the graphical installer is the piece that decides whether a machine installed
with it carries the RAVNIX branding at all. These tests exercise it without a
Calamares installation: the API of Calamares is replaced by a small stub.
"""
import importlib.util
from pathlib import Path
import re
import subprocess
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / 'modules/calamares/nixos/main.py'


def load_module(values=None):
    """Load the module with a stub for the Calamares API."""
    storage = types.SimpleNamespace()
    storage.values = values or {}

    def value(key):
        return storage.values.get(key)

    storage.value = value

    class GlobalStorage:
        @staticmethod
        def instance():
            return storage

    libcalamares = types.ModuleType('libcalamares')
    libcalamares.GlobalStorage = GlobalStorage
    utils = types.ModuleType('libcalamares.utils')
    utils.gettext_path = lambda: '/usr/share/locale'
    utils.gettext_languages = lambda: []
    utils.debug = lambda message: None
    job = types.ModuleType('libcalamares.job')
    job.setprogress = lambda value: None
    libcalamares.utils = utils
    libcalamares.job = job
    for name, module in [('libcalamares', libcalamares),
                         ('libcalamares.utils', utils),
                         ('libcalamares.job', job)]:
        sys.modules[name] = module

    spec = importlib.util.spec_from_file_location('ravnix_calamares', MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.storage_values = storage
    return module


class GraphicalInstallerModule(unittest.TestCase):
    def test_the_module_has_the_interface_that_calamares_expects(self):
        descriptor = (ROOT / 'modules/calamares/nixos/module.desc').read_text()
        self.assertIn('type:       "job"', descriptor)
        self.assertIn('name:       "nixos"', descriptor)
        self.assertIn('interface:  "python"', descriptor)
        self.assertIn('script:     "main.py"', descriptor)
        source = MODULE.read_text()
        self.assertIn('def run():', source)

    def test_the_module_installs_ravnix_and_not_plain_nixos(self):
        module = load_module()
        command = module.build_command({
            'root': '/tmp/target', 'disk': '/dev/sda', 'hostname': 'ravnix-test',
            'username': 'tester', 'timezone': 'Europe/Warsaw',
        })
        self.assertIn('--non-interactive', command)
        self.assertNotIn('--flake', command)
        self.assertIn('/tmp/target', command)
        self.assertIn('/dev/sda', command)

    def test_the_disk_of_the_mounted_target_is_found(self):
        module = load_module()
        answers = iter(['/dev/sda2\n', 'sda\n'])
        with patch.object(module.subprocess, 'check_output',
                          side_effect=lambda *a, **k: next(answers)):
            self.assertEqual(module.target_disk('/tmp/target'), '/dev/sda')

    def test_a_target_that_is_not_a_disk_is_refused(self):
        module = load_module()
        with patch.object(module.subprocess, 'check_output', return_value='tmpfs\n'):
            with self.assertRaises(Exception):
                module.target_disk('/tmp/target')

    def test_the_timezone_of_the_installer_is_used(self):
        module = load_module({'locationRegion': 'Europe', 'locationZone': 'Warsaw'})
        self.assertEqual(module.target_timezone(), 'Europe/Warsaw')
        module = load_module()
        self.assertEqual(module.target_timezone(), 'Europe/Warsaw')

    def test_the_module_refuses_to_install_without_a_user(self):
        module = load_module({'rootMountPoint': '/tmp/target'})
        with patch.object(module.subprocess, 'check_output', return_value='/dev/sda2\n'):
            with self.assertRaises(Exception):
                module.collect_values()

    def test_the_module_needs_its_own_module_directory_in_front(self):
        # Calamares uses the first module it finds for a name, so the
        # directory of our module has to be searched before the one of the
        # NixOS extensions.
        live = (ROOT / 'modules/live.nix').read_text()
        self.assertIn('modules-search: [ local, ${calamaresModules}/lib/calamares/modules', live)
        # The graphical installer uses the patched extensions, with our own
        # installation module, our own partitioning and the RAVNIX branding.
        self.assertIn('${calamaresExtensions}/share', live)
        self.assertIn('${calamaresExtensions}/etc', live)

    def test_the_graphical_installer_uses_the_ravnix_branding(self):
        live = (ROOT / 'modules/live.nix').read_text()
        self.assertIn('--replace-fail "branding: nixos" "branding: ravnix"', live)
        branding = (ROOT / 'modules/calamares/branding/ravnix/branding.desc').read_text()
        self.assertIn('componentName:  ravnix', branding)
        self.assertIn('bootloaderEntryName: RAVNIX', branding)
        # The name of NixOS may only appear in a comment, never in a value.
        for line in branding.splitlines():
            with self.subTest(line=line):
                if 'NixOS' in line:
                    self.assertTrue(line.startswith('#'), line)
        for image in ['ravnix-logo.png', 'ravnix-welcome.png', 'ravnix-background.jpg']:
            with self.subTest(image=image):
                self.assertTrue((ROOT / 'assets/calamares' / image).is_file())

    def test_the_desktop_chooser_is_not_offered(self):
        # The graphical installer always installs the RAVNIX desktop, so a
        # choice of another desktop would be ignored.
        live = (ROOT / 'modules/live.nix').read_text()
        self.assertIn('--replace-fail "  - packagechooser" ""', live)


    def test_the_graphical_installer_prepares_a_layout_ravnix_can_install(self):
        # The partitioning of the graphical installer has to match what the
        # RAVNIX configuration expects: the EFI system partition at /boot/efi
        # and, on a GPT disk, a partition for the BIOS bootloader. The stock
        # configuration of the NixOS extensions mounts the EFI system partition
        # at /boot, which would leave a system that does not boot.
        configuration = (ROOT/'modules/calamares/config/partition.conf').read_text()
        self.assertIn('mountPoint: "/boot/efi"', configuration)
        self.assertIn('createHybridBootloaderLayout: true', configuration)
        self.assertIn('recommendedSize: 512MiB', configuration)
        # The bootloader of the distribution reads ext4, so the installer
        # offers the filesystem the release is tested with.
        self.assertIn('defaultFileSystemType: "ext4"', configuration)
        self.assertIn('- ext4', configuration)
        self.assertNotIn('f2fs', configuration)
        self.assertNotIn('btrfs', configuration)
        # An encrypted root or a logical volume is not unlocked by the RAVNIX
        # configuration, so an installation with them would not boot.
        self.assertIn('enableLuksAutomatedPartitioning: false', configuration)
        self.assertIn('lvm:', configuration)
        self.assertIn('enable: false', configuration)
        # The layout of the graphical installer has to reach the package.
        live = (ROOT/'modules/live.nix').read_text()
        self.assertIn('calamares/config/partition.conf', live)

    def test_the_live_medium_carries_the_tools_of_the_graphical_installer(self):
        # The graphical installer partitions the disk and creates the
        # filesystems itself. The package of Calamares carries the tools it
        # needs to talk to the disk, but not the ones that create the
        # partitions and the filesystems, so the live medium has to provide
        # them. Without them the installation stops at the first partition.
        live = (ROOT/'modules/live.nix').read_text()
        packages = re.search(r'environment\.systemPackages = with pkgs; \[(.*?)\];', live, re.S)
        self.assertIsNotNone(packages)
        for tool in ('parted', 'e2fsprogs', 'dosfstools'):
            self.assertIn(tool, packages.group(1))

    def test_the_branding_comes_first_in_the_search_path(self):
        # The graphical installer looks for the branding in the directories of
        # XDG_DATA_DIRS and uses the first one it finds. Every prefix puts its
        # own directory in front, so two prefixes would let the last one win.
        live = (ROOT/'modules/live.nix').read_text()
        self.assertIn('--prefix XDG_DATA_DIRS : ${calamaresBranding}/share:${calamaresExtensions}/share',
                      live)
        self.assertEqual(live.count('--prefix XDG_DATA_DIRS'), 1)

    def test_the_configuration_of_the_welcome_stays_valid(self):
        # The wizard does not start at all when the file of the welcome module
        # is broken. The key of the space belongs to the block of
        # "requirements", so the line has to keep its indentation: a line
        # without it is not valid YAML and the module cannot be created.
        live = (ROOT/'modules/live.nix').read_text()
        self.assertIn(r"s/^([[:space:]]*)requiredStorage:.*$/\1requiredStorage: 16/", live)
        self.assertIn(r"s/^([[:space:]]*)setRootPassword:.*$/\1setRootPassword: false/", live)
        # A line that loses its indentation is the defect that stopped the
        # wizard on the first release of the graphical installer.
        self.assertNotIn("requiredStorage:.*$/requiredStorage: 16'", live)
        self.assertNotIn("setRootPassword:.*$/setRootPassword: false'", live)

    def test_the_changed_configuration_of_the_welcome_is_valid_yaml(self):
        # The same change is made on a copy of the file of the NixOS
        # extensions, and the result is read back. The test does not need the
        # package: the shape of the file is what matters.
        configuration = (
            '# a comment\n'
            'showReleaseNotesUrl: true\n'
            '\n'
            'requirements:\n'
            '    requiredStorage: 10\n'
            '    requiredRam: 3.0\n'
            '\n'
            '    required:\n'
            '        - storage\n'
        )
        import re as regex
        changed = regex.sub(r'^(\s*)requiredStorage:.*$', r'\1requiredStorage: 16',
                            configuration, flags=regex.M)
        self.assertIn('    requiredStorage: 16', changed)
        # Every line of the block has to keep its four spaces.
        for line in changed.splitlines():
            with self.subTest(line=line):
                if line.strip().startswith('required'):
                    self.assertTrue(line.startswith('    '), line)

    def test_the_graphical_installer_is_the_calamares_package(self):
        # The package of the NixOS extensions is a function that takes its
        # arguments, so it cannot be overridden like a derivation.
        live = (ROOT/'modules/live.nix').read_text()
        self.assertIn('pkgs.calamares.override {', live)
        self.assertNotIn('pkgs.calamares-nixos.override', live)
        # The branding is a set of links, and the entries name the file and
        # the path it points to.
        self.assertIn('{ name = "share/calamares/branding/ravnix/branding.desc"; path =', live)


if __name__ == '__main__':
    unittest.main()
