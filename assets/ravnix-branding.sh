#!/bin/sh
# RAVNIX branding — enforce the Purple Neon colour scheme and the custom
# wallpaper once the Plasma shell is up.
#
# The shell owns the desktop D-Bus interface that both apply-tools talk to,
# so the session has to exist before anything is applied. Running late is
# harmless: the tools only set state, they do not draw.
set -u

wallpaper=/run/current-system/sw/share/backgrounds/ravnix/ravnix-wallpaper.jpg
scheme=RAVNIX-PurpleNeon

# Wait for plasma-shell, but never block the session for longer than a minute.
waited=0
while [ "$waited" -lt 60 ]; do
	if pgrep -x plasma-shell >/dev/null 2>&1; then
		break
	fi
	waited=$((waited + 1))
	sleep 1
done

# The shell publishes its containment list slightly after it starts.
sleep 2

if [ ! -f "$wallpaper" ]; then
	# Fall back to any XDG data directory that carries the branding.
	for dir in ${XDG_DATA_DIRS:-}; do
		if [ -f "$dir/backgrounds/ravnix/ravnix-wallpaper.jpg" ]; then
			wallpaper="$dir/backgrounds/ravnix/ravnix-wallpaper.jpg"
			break
		fi
	done
fi

if command -v plasma-apply-colorscheme >/dev/null 2>&1; then
	plasma-apply-colorscheme "$scheme" >/dev/null 2>&1 || true
fi

if [ -f "$wallpaper" ] && command -v plasma-apply-wallpaperimage >/dev/null 2>&1; then
	# preserveAspectFit keeps the artwork whole; the other accepted values are
	# stretch, preserveAspectCrop and pad.
	plasma-apply-wallpaperimage "$wallpaper" --fill-mode preserveAspectFit >/dev/null 2>&1 || true
fi
