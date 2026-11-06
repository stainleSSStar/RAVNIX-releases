#!/usr/bin/env python3
"""Compare the paths an installation builds with the paths the live image carries.

The live image carries the whole desktop closure, so an installation mostly
copies it. The paths that the live image does not carry are the ones the
installation has to build itself: configuration artefacts such as rendered
files, systemd units, the initial ramdisk or the system profile. Their inputs
are small scripts that come from the Nixpkgs source, so nix rebuilds them
locally in a few minutes.

A source that the live image does not carry and that is a package source is a
problem. The installation would have to download it and compile it, which
needs a network connection and a compiler, and which takes hours on a slow
machine. This script reports those sources and fails when there are any.

Usage: check-install-plan.py LIVE.json TARGET.json TOPLEVEL.drv
"""
import json
import sys

# Sources of packages: a source tree, a release archive or a single file that
# was fetched from a repository. Everything else is a file of the Nixpkgs
# source tree, such as the script that renders a systemd unit.
ARCHIVES = ('.tar', '.tgz', '.tar.gz', '.tar.xz', '.tar.bz2', '.zip', '.xz', '.gz', '.bz2')


def load(path):
    with open(path, encoding='utf-8') as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def paths_of(derivations):
    """Every path the store holds for these derivations."""
    paths = set()
    for info in derivations.values():
        if not isinstance(info, dict):
            continue
        paths.update(info.get('outputs') or {})
        paths.update(info.get('inputSources') or [])
    return paths


def is_package_source(path):
    """True when the path is a fetched source tree or a release archive."""
    name = path.rsplit('/', 1)[-1]
    if name.endswith('-source'):
        return True
    return any(name.endswith(archive) for archive in ARCHIVES)


def main():
    live = load(sys.argv[1])
    target = load(sys.argv[2])
    toplevel = sys.argv[3]

    live_paths = paths_of(live)

    # The configuration itself is copied into the new system and read from
    # there, so its source never comes from the network.
    configuration = set((target.get(toplevel) or {}).get('inputSources') or [])

    missing = sorted(set(target) - set(live))
    print(f'The installation builds {len(missing)} paths that the live image does not carry.')
    for name in missing[:40]:
        print(f'  {name.rsplit("/", 1)[-1]}')
    if len(missing) > 40:
        print(f'  ... and {len(missing) - 40} more')

    sources = set()
    for name in missing:
        info = target.get(name) or {}
        for source in (info.get('inputSources') or []):
            if source in live_paths or source in configuration:
                continue
            if is_package_source(source):
                sources.add(source)

    if not sources:
        print('OK: nothing has to be downloaded.')
        return 0

    print('Sources the installation would have to download:')
    for source in sorted(sources):
        print(f'  {source.rsplit("/", 1)[-1]}')
    print('ERROR: the installation depends on packages that the live image does not carry.',
          file=sys.stderr)
    return 1


if __name__ == '__main__':
    sys.exit(main())
