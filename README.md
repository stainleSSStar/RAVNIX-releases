# RAVNIX releases

Public downloads for **RAVNIX**, a minimal x86_64 NixOS 26.05 console distribution.

**[Download tested releases](https://github.com/stainleSSStar/RAVNIX-releases/releases)**

**Poradnik po polsku: [instalowanie programów i ręczne dodanie pulpitu XFCE](docs/PROGRAMY-I-PULPIT-PL.md).**

Fish, Ethernet/Wi-Fi networking, essential firmware, BIOS/UEFI boot and a text
installer. No graphical stack, desktop, browser, audio server or SSH server.
The build/source repository is maintained separately and remains private.

Each release includes the ISO, `SHA256SUMS`, guide, exact source/Nixpkgs revisions,
lockfile, closure manifest and real VM test logs. A release is published only
after BIOS and UEFI live, installation, password login/sudo, rebuild and reboot
tests succeed. Verify the checksum before writing the image:

```sh
sha256sum -c SHA256SUMS
```

On macOS, use `shasum -a 256 ravnix-26.05-x86_64.iso` and compare with SHA256SUMS.

Boot with Secure Boot disabled. Connect networking using `nmtui`, then run:

```sh
sudo ravnix-install
```

**Installation erases the whole selected disk after explicit confirmation.**
Use a dedicated disk of at least 16 GiB. No dual boot, encryption/LVM or RAID
setup. Read the bundled `GUIDE.md` before installation. Physical hardware still
needs testing on the intended machines; successful VM tests are not a guarantee
of compatibility with every device.

RAVNIX is a derivative, not an official NixOS release. Included software retains
its own licenses; see the source/configuration included with the live image.
