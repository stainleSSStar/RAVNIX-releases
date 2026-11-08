#!/bin/sh
# RAVNIX branding — bring the desktop into the look of RAVNIX.
#
# The Plasma shell owns the D-Bus interface that the apply-tools talk to, so
# the session has to exist before anything can be applied. The shell also
# writes the layout of the desktop when it starts, and it throws away a
# wallpaper that was set before that moment: the wallpaper of RAVNIX was seen
# only a minute or two after the login, and the desktop of the user showed
# the standard picture until then. The script therefore waits for the shell,
# and only then it sets the wallpaper.
#
# The colours are applied once. A script that puts them back every second
# would take the choice of the user in the settings of the desktop away
# again, and that is exactly what a user complained about: the theme of the
# desktop never changed, because the script changed it back right after the
# user had chosen another one. A marker in the profile of the user keeps the
# script from ever doing that again.
#
# The wallpaper is only set when the desktop has no picture that works. A
# picture that the user chose is never thrown away.
set -u

scheme=RAVNIX-PurpleNeon
wallpaper_name=ravnix-wallpaper.jpg
# How long the script keeps trying. A slow machine needs more than the
# first second to bring the shell up, and the script may also start before
# the session is ready at all.
attempts=180

config_home="${XDG_CONFIG_HOME:-$HOME/.config}"
applets="$config_home/plasma-org.kde.plasma.desktop-appletsrc"
globals="$config_home/kdeglobals"
state_dir="$config_home/ravnix"
marker="$state_dir/branding-applied"

warn() {
	echo "ravnix-branding: $*" >&2
}

# The service of the session and the entry in the autostart of the desktop
# start the script at the same moment. Only one of them may work, otherwise
# both set the wallpaper of the desktop at the same time.
#
# A lock that is older than five minutes is left over from a session that was
# killed, and it is taken over. Otherwise the desktop of that account would
# never be branded again.
lock="$state_dir/branding.lock"
take_lock() {
	mkdir -p "$state_dir" 2>/dev/null || return 1
	mkdir "$lock" 2>/dev/null && return 0
	# A lock that is older than five minutes is left over from a session
	# that was killed, and it is taken over. Otherwise the desktop of that
	# account would never be branded again.
	find "$lock" -maxdepth 0 -mmin +5 2>/dev/null | grep -q . || return 1
	rmdir "$lock" 2>/dev/null || true
	mkdir "$lock" 2>/dev/null
}
if ! take_lock; then
	exit 0
fi
trap 'rmdir "$lock" 2>/dev/null || true' 0
trap 'exit 0' 1 2 15

# --- the picture of the distribution ------------------------------------
# The wallpaper belongs to the profile of the system, but a session that does
# not carry the profile in its data directories still has to find it.
wallpaper=
for dir in ${XDG_DATA_DIRS:-} /run/current-system/sw/share; do
	if [ -f "$dir/backgrounds/ravnix/$wallpaper_name" ]; then
		wallpaper="$dir/backgrounds/ravnix/$wallpaper_name"
		break
	fi
done
if [ -z "$wallpaper" ]; then
	warn "the wallpaper of RAVNIX was not found."
	exit 0
fi

# --- the colours of the distribution ------------------------------------
# The desktop reads the colours from the files that end in ".colors". The
# scheme of RAVNIX has to be found there, otherwise the desktop falls back
# to the standard colours and the panel stays white.
scheme_file=
for dir in ${XDG_DATA_DIRS:-} /run/current-system/sw/share "$HOME/.local/share"; do
	if [ -f "$dir/color-schemes/$scheme.colors" ]; then
		scheme_file="$dir/color-schemes/$scheme.colors"
		break
	fi
done
if [ -z "$scheme_file" ]; then
	warn "the colour scheme $scheme was not found."
	exit 0
fi

# --- the state of the desktop -------------------------------------------
# The picture the desktop shows right now. An empty answer means that the
# desktop has no picture at all.
#
# The shell writes the entries of a group either on lines of their own or
# behind the name of the group, and the entries of a group are separated by
# commas. The separators are therefore turned into line breaks, so the entry
# of the picture can be found in every way the shell writes it.
current_wallpaper() {
	[ -f "$applets" ] || return 0
	tr ',' '\n' < "$applets" 2>/dev/null \
		| tr ' ' '\n' \
		| grep -m 1 '^Image=' \
		| sed 's|^Image=||'
}

# The desktop has a picture that works when the answer is a path to a file
# that is really there. The name of a wallpaper of the desktop is a choice of
# the user as well, and it is only kept when the package of that wallpaper is
# really installed: a global theme of KDE asks for a wallpaper that RAVNIX
# does not ship, and the desktop would show nothing at all.
wallpaper_broken() {
	current=$(current_wallpaper)
	case "$current" in
	file://*)
		file=${current#file://}
		[ -f "$file" ] && return 1
		return 0
		;;
	"")
		return 0
		;;
	*)
		for dir in ${XDG_DATA_DIRS:-} /run/current-system/sw/share; do
			[ -d "$dir/plasma/wallpapers/$current" ] && return 1
		done
		return 0
		;;
	esac
}

# The name of the colours in the configuration of the desktop.
scheme_in_globals() {
	[ -f "$globals" ] || return 1
	grep -q "^ColorScheme=$scheme\$" "$globals" 2>/dev/null
}

# The shell has written the layout of the desktop. The wallpaper may only be
# set after that, because the shell throws away everything that was set
# before it.
shell_ready() {
	[ -f "$applets" ] || return 1
	grep -qi 'wallpaperplugin' "$applets" 2>/dev/null
}

count=0
while [ "$count" -lt 60 ]; do
	shell_ready && break
	count=$((count + 1))
	sleep 1
done

# --- the wallpaper -------------------------------------------------------
if wallpaper_broken; then
	if ! command -v plasma-apply-wallpaperimage >/dev/null 2>&1; then
		warn "the tools of the desktop are not in the session."
		exit 0
	fi
	count=0
	while [ "$count" -lt "$attempts" ]; do
		# preserveAspectFit keeps the artwork whole; the other accepted values
		# are stretch, preserveAspectCrop and pad.
		plasma-apply-wallpaperimage "$wallpaper" --fill-mode preserveAspectFit >/dev/null 2>&1 || true
		wallpaper_broken || break
		count=$((count + 1))
		sleep 1
	done
	if wallpaper_broken; then
		warn "the wallpaper was not applied."
	fi
fi

# --- the colours ---------------------------------------------------------
# The colours are applied once, and the marker remembers that they are there.
if [ ! -f "$marker" ]; then
	applied=0
	if command -v plasma-apply-colorscheme >/dev/null 2>&1; then
		count=0
		while [ "$count" -lt 30 ]; do
			if plasma-apply-colorscheme "$scheme" >/dev/null 2>&1; then
				applied=1
				break
			fi
			count=$((count + 1))
			sleep 1
		done
	fi
	# The desktop writes the name of the colours into its own configuration,
	# and that is the proof that the colours are really in place.
	if [ "$applied" -eq 1 ] || scheme_in_globals; then
		: > "$marker" 2>/dev/null || true
	fi
fi

exit 0
