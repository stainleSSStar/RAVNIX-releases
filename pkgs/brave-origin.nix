# Brave Origin — the standalone, feature-stripped Brave build that is free on
# Linux. It is not in nixpkgs (only the full "brave" package is), so RAVNIX
# repackages the official .deb here.
#
# The upstream project publishes one .deb per release in Brave's apt pool:
#   https://brave-browser-apt-release.s3.brave.com/pool/main/b/brave-origin/
# Bump `version` and `hash` together; scripts/update-brave-origin.sh prints
# both for a new release.
#
# The layout mirrors nixpkgs' own `brave` package (pkgs/by-name/br/brave),
# which repackages the same way.
{ lib
, stdenv
, buildPackages
, fetchurl
, dpkg
, gnutar
, patchelf
, xdg-utils
, coreutils
, glib
, gsettings-desktop-schemas
, gtk3
, gtk4
, adwaita-icon-theme
, alsa-lib
, at-spi2-atk
, at-spi2-core
, atk
, cairo
, cups
, dbus
, expat
, fontconfig
, freetype
, gdk-pixbuf
, libdrm
, libx11
, libGL
, libxkbcommon
, libxscrnsaver
, libxcomposite
, libxcursor
, libxdamage
, libxext
, libxfixes
, libxi
, libxrandr
, libxrender
, libxshmfence
, libxtst
, libuuid
, libgbm
, nspr
, nss
, pango
, pipewire
, udev
, wayland
, libxcb
, zlib
, snappy
, libkrb5
, qt6
, libpulseaudio
, libva
}:

let
  inherit (lib)
    makeBinPath
    makeLibraryPath
    makeSearchPathOutput
    ;

  # Shared libraries the prebuilt binary dlopen()s at runtime. They have to be
  # baked into the ELF RUNPATH: the .deb expects Debian's /usr/lib layout.
  deps = [
    alsa-lib
    at-spi2-atk
    at-spi2-core
    atk
    cairo
    cups
    dbus
    expat
    fontconfig
    freetype
    gdk-pixbuf
    glib
    gtk3
    gtk4
    libdrm
    libx11
    libGL
    libxkbcommon
    libxscrnsaver
    libxcomposite
    libxcursor
    libxdamage
    libxext
    libxfixes
    libxi
    libxrandr
    libxrender
    libxshmfence
    libxtst
    libuuid
    libgbm
    nspr
    nss
    pango
    pipewire
    udev
    wayland
    libxcb
    zlib
    snappy
    libkrb5
    qt6.qtbase
    libpulseaudio
    libva
  ];

  rpath = makeLibraryPath deps + ":" + makeSearchPathOutput "lib" "lib64" deps;
  binpath = makeBinPath deps;
in
stdenv.mkDerivation {
  pname = "brave-origin";
  version = "1.98.63";

  src = fetchurl {
    url = "https://brave-browser-apt-release.s3.brave.com/pool/main/b/brave-origin/brave-origin_1.98.63_amd64.deb";
    hash = "sha256-7b2eyO1VmShI/2iJYX+V1OnvFiW9ouWKLSJv9WBNScg=";
  };

  nativeBuildInputs = [
    dpkg
    gnutar
    patchelf
    # Same wrapper nixpkgs' `brave` uses: it supplies the GSettings schema
    # directory, the gdk-pixbuf loader cache, the dconf GIO module and the
    # icon theme at runtime.
    (buildPackages.wrapGAppsHook3.override { makeWrapper = buildPackages.makeShellWrapper; })
  ];
  buildInputs = [
    glib
    gsettings-desktop-schemas
    gtk3
    gtk4
    adwaita-icon-theme
  ];

  dontConfigure = true;
  dontBuild = true;
  dontPatchELF = true;
  doInstallCheck = true;

  unpackPhase = ''
    runHook preUnpack
    # Do not use "dpkg-deb -x": it calls tar with -p, which fails when the
    # archive contains a setuid file - the chrome-sandbox helper here. Extract
    # the file tree with plain tar instead, exactly like the dpkg setup hook
    # in nixpkgs does.
    mkdir root
    dpkg-deb --fsys-tarfile "$src" | ${gnutar}/bin/tar --extract --directory=root
    runHook postUnpack
  '';

  installPhase = ''
    runHook preInstall

    mkdir -p "$out/bin"
    cp -R root/usr/share "$out"
    cp -R root/opt "$out/opt"

    # The .deb ships a small bash launcher next to the real binary.
    export BINARYWRAPPER="$out/opt/brave.com/brave-origin/brave-origin"

    substituteInPlace "$BINARYWRAPPER" \
      --replace-fail /bin/bash ${stdenv.shell} \
      --replace-fail 'CHROME_WRAPPER' 'WRAPPER'

    ln -sf "$BINARYWRAPPER" "$out/bin/brave-origin"

    # The setuid sandbox helper cannot work from the Nix store: the store is
    # read-only and the helper would have to be owned by root with mode 4755.
    # Chromium refuses to start when it finds a helper that is present but not
    # configured that way, so drop it and let the browser fall back to the
    # unprivileged user-namespace sandbox, which NixOS allows by default.
    # The helper is not shipped and the browser is not told to skip the
    # sandbox: the user namespace sandbox is a real sandbox and it is the one
    # the browser uses on its own.
    rm -f "$out/opt/brave.com/brave-origin/chrome-sandbox"

    for exe in "$out/opt/brave.com/brave-origin/brave" \
                "$out/opt/brave.com/brave-origin/chrome_crashpad_handler"; do
      patchelf \
        --set-interpreter "$(cat "$NIX_CC/nix-support/dynamic-linker")" \
        --set-rpath "${rpath}" "$exe"
    done

    for desktop in "$out/share/applications/brave-origin.desktop" \
                   "$out/share/applications/com.brave.Origin.desktop"; do
      # Only the launcher path is referenced by the .desktop files; there is no
      # /opt/brave.com entry to rewrite in them.
      substituteInPlace "$desktop" \
        --replace-fail /usr/bin/brave-origin-stable "$out/bin/brave-origin"
    done

    # The default browser chooser points at the wrapper as well, so the browser
    # still starts with its runtime environment.
    substituteInPlace "$out/opt/brave.com/brave-origin/default-app-block" \
      --replace-fail /opt/brave.com/brave-origin/brave-origin "$out/bin/brave-origin"

    icon_sizes=( "16" "24" "32" "48" "64" "128" "256" )
    for icon in ''${icon_sizes[*]}; do
      mkdir -p "$out/share/icons/hicolor/$icon"'x'"$icon/apps"
      ln -s "$out/opt/brave.com/brave-origin/product_logo_$icon.png" \
        "$out/share/icons/hicolor/$icon"'x'"$icon/apps/brave-origin.png"
    done

    ln -sf ${xdg-utils}/bin/xdg-settings "$out/opt/brave.com/brave-origin/xdg-settings"
    ln -sf ${xdg-utils}/bin/xdg-mime "$out/opt/brave.com/brave-origin/xdg-mime"

    runHook postInstall
  '';

  preFixup = ''
    gappsWrapperArgs+=(
      --prefix LD_LIBRARY_PATH : ${rpath}
      --prefix PATH : ${binpath}
      --suffix PATH : ${makeBinPath [ xdg-utils coreutils ]}
      --set CHROME_WRAPPER brave-origin
      --add-flags "--disable-features=OutdatedBuildDetector"
      --add-flags "--ozone-platform-hint=auto"
      --add-flags "--enable-features=AcceleratedVideoDecodeLinuxGL,AcceleratedVideoEncoder"
    )
  '';

  installCheckPhase = ''
    # Bypass the upstream launcher, which swallows the exit status.
    timeout 300 "$out/opt/brave.com/brave-origin/brave" --version
    # The wrapper chain users actually run has to print the version as well:
    # the GApps wrapper, the upstream launcher and the browser. This is the
    # same assertion the virtual machine test makes on the installed system.
    timeout 300 "$out/bin/brave-origin" --version > "$TMPDIR/ravnix-brave-version.txt" 2>&1 || true
    cat "$TMPDIR/ravnix-brave-version.txt"
    grep -qiE 'brave|chromium' "$TMPDIR/ravnix-brave-version.txt"
    grep -qE '[0-9]+[.][0-9]+' "$TMPDIR/ravnix-brave-version.txt"
  '';

  meta = {
    homepage = "https://brave.com/origin/";
    description = "Brave Origin — stripped-down Brave browser, free on Linux";
    license = lib.licenses.mpl20;
    platforms = [ "x86_64-linux" "aarch64-linux" ];
    mainProgram = "brave-origin";
  };
}
