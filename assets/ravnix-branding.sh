#!/bin/sh
# RAVNIX branding — enforce the Purple Neon colour scheme and the custom
# wallpaper once the Plasma shell is up.
#
# The shell owns the desktop D-Bus interface that both apply-tools talk to,
# so the session has to exist before anything can be applied. The first
# attempt always comes too early, and a single attempt that fails leaves
# the desktop with the default wallpaper for the rest of the session, so
# the script keeps trying until the wallpaper really is in the
# configuration of the desktop.
set -u

scheme=RAVNIX-PurpleNeon
# How long the script keeps trying. A slow machine needs more than the
# first second to bring the shell up, and the script may also start before
# the session is ready at all.
attempts=180

# The wallpaper belongs to the profile of the system, but a session that
# does not carry the profile in its data directories still has to find it.
wallpaper=
for dir in ${XDG_DATA_DIRS:-}; do
	if [ -f "$dir/backgrounds/ravnix/ravnix-wallpaper.jpg" ]; then
		wallpaper="$dir/backgrounds/ravnix/ravnix-wallpaper.jpg"
		break
	fi
done
if [ -z "$wallpaper" ]; then
	if [ -f /run/current-system/sw/share/backgrounds/ravnix/ravnix-wallpaper.jpg ]; then
		wallpaper=/run/current-system/sw/share/backgrounds/ravnix/ravnix-wallpaper.jpg
	fi
fi
if [ -z "$wallpaper" ]; then
	echo "ravnix-branding: the RAVNIX wallpaper was not found." >&2
	exit 1
fi

apply_scheme() {
	command -v plasma-apply-colorscheme >/dev/null 2>&1 || return 1
	plasma-apply-colorscheme "$scheme" >/dev/null 2>&1
}

apply_wallpaper() {
	command -v plasma-apply-wallpaperimage >/dev/null 2>&1 || return 1
	# preserveAspectFit keeps the artwork whole; the other accepted values
	# are stretch, preserveAspectCrop and pad.
	plasma-apply-wallpaperimage "$wallpaper" --fill-mode preserveAspectFit >/dev/null 2>&1
}

# The desktop writes the wallpaper into its own configuration file. The file
# is the proof that the wallpaper is really in place, not just that the
# command was sent.
applied() {
	config="${XDG_CONFIG_HOME:-$HOME/.config}/plasma-org.kde.plasma.desktop-appletsrc"
	[ -f "$config" ] || return 1
	grep -q "ravnix-wallpaper.jpg" "$config" 2>/dev/null
}

count=0
wallpaper_done=0
while [ "$count" -lt "$attempts" ]; do
	apply_wallpaper || true
	if applied; then
		wallpaper_done=1
		break
	fi
	count=$((count + 1))
	sleep 1
done

# The colours are applied once, after the wallpaper is there. A script that
# puts them back every second would take the choice of the user away again:
# the desktop would fall back to the colours of RAVNIX right after the user
# picked another theme in the settings.
count=0
while [ "$count" -lt 10 ]; do
	apply_scheme && break
	count=$((count + 1))
	sleep 1
done

if [ "$wallpaper_done" -ne 1 ]; then
	echo "ravnix-branding: the wallpaper was not applied." >&2
	exit 1
fi
exit 0
