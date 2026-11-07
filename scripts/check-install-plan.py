#!/usr/bin/env python3
"""Compare the derivations and sources of an installation with the live image.

The live image carries the whole desktop closure, so an installation mostly
copies it. The derivations that the live image does not carry are the ones the
installation has to build itself: configuration artefacts such as rendered
files, systemd units, the initial ramdisk or the system profile. Their inputs
are small scripts that come from the Nixpkgs source, so nix rebuilds them
locally in a few minutes.

A source that the live image does not carry and that is a package source is a
problem. The installation would have to download it and compile it, which
needs a network connection and a compiler, and which takes hours on a slow
machine. This script reports those sources and fails when there are any.

Usage: check-install-plan.py LIVE-requisites.txt TARGET-requisites.txt [CONFIGURATION]
"""
import sys

# Sources of packages: a source tree or a release archive. Everything else is
# a single file of the Nixpkgs source tree, such as the script that renders a
# systemd unit.
ARCHIVES = ('.tar', '.tgz', '.tar.gz', '.tar.xz', '.tar.bz2', '.zip', '.xz', '.gz', '.bz2')


def read(path):
    with open(path, encoding='utf-8') as handle:
        return [line.strip() for line in handle if line.strip()]


def derivations(paths):
    return {path for path in paths if path.endswith('.drv')}


def sources(paths):
    return {path for path in paths if not path.endswith('.drv')}


def is_package_source(path):
    """True when the path is a fetched source tree or a release archive."""
    name = path.rsplit('/', 1)[-1]
    if name.endswith('-source'):
        return True
    return any(name.endswith(archive) for archive in ARCHIVES)


def main():
    live = read(sys.argv[1])
    target = read(sys.argv[2])
    configuration = sys.argv[3] if len(sys.argv) > 3 else ''

    live_derivations = derivations(live)
    live_sources = sources(live)
    target_derivations = derivations(target)
    target_sources = sources(target)

    missing_derivations = sorted(target_derivations - live_derivations)
    missing_sources = sorted(target_sources - live_sources - {configuration})

    print(f'The live image carries {len(live_derivations)} derivations and '
          f'{len(live_sources)} sources, the installation needs '
          f'{len(target_derivations)} derivations and {len(target_sources)} sources.')
    print(f'The installation builds {len(missing_derivations)} derivations that the '
          'live image does not carry.')
    for name in missing_derivations[:20]:
        print(f'  {name.rsplit("/", 1)[-1]}')
    if len(missing_derivations) > 20:
        print(f'  ... and {len(missing_derivations) - 20} more')

    packages = [source for source in missing_sources if is_package_source(source)]
    if not packages:
        print('OK: nothing has to be downloaded.')
        return 0

    print('Sources the installation would have to download:')
    for source in packages:
        print(f'  {source.rsplit("/", 1)[-1]}')
    print('ERROR: the installation depends on packages that the live image does not carry.',
          file=sys.stderr)
    return 1


if __name__ == '__main__':
    sys.exit(main())
