# Brave Origin — the standalone, feature-stripped Brave build that is free on
# Linux. It is not in nixpkgs (only the full "brave" package is), so RAVNIX
# repackages the official .deb here.
#
# The upstream project publishes one .deb per release in Brave's apt pool:
#   https://brave-browser-apt-release.s3.brave.com/pool/main/b/brave-origin/
# Bump `version` and `hash` together; scripts/update-brave-origin.sh prints
# both for a new release.
{ lib
, stdenv
, fetchurl
, dpkg
, patchelf
, xdg-utils
, makeWrapper
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
, glib
, gtk3
, gtk4
, libdrm
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
  ]
  ++ [ libpulseaudio libva ];

  rpath = makeLibraryPath deps + ":" + makeSearchPathOutput "lib" "lib64" deps;
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
    patchelf
    makeWrapper
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

  unpackPhase = ''
    runHook preUnpack
    dpkg-deb -x "$src" .
    runHook postUnpack
  '';

  installPhase = ''
    runHook preInstall

    mkdir -p "$out/bin"
    cp -R usr/share "$out"
    cp -R opt "$out/opt"

    # The .deb ships a small bash launcher next to the real binary.
    export BINARYWRAPPER="$out/opt/brave.com/brave-origin/brave-origin"

    substituteInPlace "$BINARYWRAPPER" \
      --replace-fail /bin/bash ${stdenv.shell} \
      --replace-fail 'CHROME_WRAPPER' 'WRAPPER'

    ln -sf "$BINARYWRAPPER" "$out/bin/brave-origin"

    for exe in "$out/opt/brave.com/brave-origin/brave" \
                "$out/opt/brave.com/brave-origin/chrome_crashpad_handler"; do
      patchelf \
        --set-interpreter "$(cat "$NIX_CC/nix-support/dynamic-linker")" \
        --set-rpath "${rpath}" "$exe"
    done

    for desktop in "$out/share/applications/brave-origin.desktop" \
                   "$out/share/applications/com.brave.Origin.desktop"; do
      substituteInPlace "$desktop" \
        --replace-fail /usr/bin/brave-origin-stable "$out/bin/brave-origin" \
        --replace-fail /opt/brave.com "$out/opt/brave.com"
    done

    substituteInPlace "$out/opt/brave.com/brave-origin/default-app-block" \
      --replace-fail /opt/brave.com "$out/opt/brave.com"

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

  meta = {
    homepage = "https://brave.com/origin/";
    description = "Brave Origin — stripped-down Brave browser, free on Linux";
    license = lib.licenses.mpl20;
    platforms = [ "x86_64-linux" "aarch64-linux" ];
    mainProgram = "brave-origin";
  };
}
