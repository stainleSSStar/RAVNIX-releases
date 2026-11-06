#!/usr/bin/env python3
"""Compare the paths an installation builds with the paths the live image carries.

The live image carries the whole desktop closure, so an installation mostly
copies it. The paths that the live image does not carry are the ones the
installation has to build itself: configuration artefacts such as rendered
files, systemd units, the initial ramdisk or the system profile. Their inputs
are small scripts, so nix rebuilds them locally in a few minutes.

A path that needs a source the live image does not carry is a package. The
installation would have to download that source and compile it, which needs a
network connection and a compiler, and which takes hours on a slow machine.
This script reports those sources and fails when there are any.

Usage: check-install-plan.py LIVE.json TARGET.json TOPLEVEL.drv [LIMIT]
"""
import json
import sys
import urllib.request

CACHE = 'https://cache.nixos.org'


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


def download_size(path):
    """The size of a path in the binary cache, or None when it is unknown."""
    name = path.rsplit('/', 1)[-1]
    digest = name.split('-', 1)[0]
    if len(digest) != 32:
        return None
    try:
        with urllib.request.urlopen(f'{CACHE}/{digest}.narinfo', timeout=15) as response:
            for line in response.read().decode('utf-8', 'replace').splitlines():
                if line.startswith('FileSize:'):
                    return int(line.split(':', 1)[1].strip())
    except Exception:
        return None
    return None


def main():
    live = load(sys.argv[1])
    target = load(sys.argv[2])
    toplevel = sys.argv[3]
    limit = int(sys.argv[4]) if len(sys.argv) > 3 else 1024 * 1024

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
            if source not in live_paths and source not in configuration:
                sources.add(source)

    if not sources:
        print('OK: nothing has to be downloaded.')
        return 0

    print('Sources the installation would have to download:')
    total = 0
    for source in sorted(sources):
        size = download_size(source)
        total += size or 0
        print(f'  {source.rsplit("/", 1)[-1]}'
              + (f' ({size} bytes)' if size is not None else ' (size unknown)'))
    print(f'Total download: {total} bytes.')
    if total > limit:
        print(f'ERROR: the installation depends on more than {limit} bytes from the network.',
              file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
