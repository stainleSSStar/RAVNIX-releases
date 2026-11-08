#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The installation step of the RAVNIX graphical installer.

The stock Calamares module for NixOS writes a configuration of its own and
installs plain NixOS, so a machine installed with it has none of the RAVNIX
branding. This module installs the pinned RAVNIX configuration instead: the
graphical installer ends with the same system as the text installer, with the
Purple Neon theme, the wallpaper, Fish, Brave Origin and the branded
bootloader.

The graphical installer has already partitioned the disk, mounted the target
and collected the hostname, the user and the timezone. The installation itself
is done by the RAVNIX installer, which is the same program the text installer
runs, so both paths cannot drift apart.
"""
import gettext
import os
import subprocess
import tempfile

import libcalamares
import libcalamares.utils

_ = gettext.translation(
    "calamares-python",
    localedir=libcalamares.utils.gettext_path(),
    languages=libcalamares.utils.gettext_languages(),
    fallback=True,
).gettext

# The absolute path of the RAVNIX installer. The name alone is not enough:
# pkexec resets the environment, so the store path of the program is needed.
INSTALLER = "@ravnixInstaller@"


def storage():
    """The values that the graphical installer collected."""
    return libcalamares.GlobalStorage.instance()


def target_disk(root_mount_point):
    """The whole disk that holds the mounted target."""
    source = subprocess.check_output(
        ["findmnt", "--noheadings", "--output", "SOURCE", "--target", root_mount_point],
        text=True,
    ).strip()
    if source.startswith("/dev/mapper/"):
        raise RuntimeError(
            "The target is encrypted or on a logical volume, which RAVNIX does "
            "not install on: " + source
        )
    if not source.startswith("/dev/"):
        raise RuntimeError("The target is not on a block device: " + source)
    parent = subprocess.check_output(
        ["lsblk", "--noheadings", "--output", "PKNAME", source], text=True
    ).strip().split()
    if not parent:
        raise RuntimeError("Cannot find the disk that holds " + source)
    return "/dev/" + parent[0]


def target_timezone():
    """The timezone that the locale module collected."""
    values = storage()
    region = values.value("locationRegion")
    zone = values.value("locationZone")
    if region and zone:
        return region + "/" + zone
    return "Europe/Warsaw"


def build_command(values):
    """The command that installs RAVNIX on the prepared target."""
    return [
        INSTALLER,
        "--non-interactive",
        "--root",
        values["root"],
        "--disk",
        values["disk"],
        "--hostname",
        values["hostname"],
        "--username",
        values["username"],
        "--timezone",
        values["timezone"],
    ]


def collect_values():
    """Everything the installation needs, taken from the graphical installer."""
    values = storage()
    root = values.value("rootMountPoint")
    username = values.value("username")
    if not root:
        raise RuntimeError("The graphical installer did not mount the target.")
    if not username:
        raise RuntimeError("The graphical installer did not collect a user name.")
    return {
        "root": root,
        "disk": target_disk(root),
        "hostname": values.value("hostname") or "ravnix",
        "username": username,
        "timezone": target_timezone(),
    }


def run():
    """Install RAVNIX on the target that the graphical installer prepared."""
    libcalamares.job.setprogress(0.01)
    try:
        values = collect_values()
        command = build_command(values)
    except Exception as error:
        return (_("Cannot prepare the RAVNIX installation"), str(error))
    if os.geteuid() != 0:
        # The graphical installer runs as the live user, the installation
        # itself needs the root rights.
        command = ["pkexec"] + command
    libcalamares.utils.debug("ravnix-install: " + " ".join(command))
    # The output of the installation goes to the console of the installer, so
    # the user can see how far it is. The error output is kept aside, because
    # the reason for a failure belongs in the message of the failed step.
    with tempfile.TemporaryFile() as errors:
        try:
            subprocess.check_call(command, stderr=errors)
        except subprocess.CalledProcessError as error:
            errors.seek(0)
            reason = errors.read().decode("utf-8", "replace").strip().splitlines()
            return (_("The RAVNIX installation failed"), "\n".join(reason[-10:]) or str(error))
        except Exception as error:
            return (_("The RAVNIX installation failed"), str(error))
    libcalamares.job.setprogress(1.0)
    return None
