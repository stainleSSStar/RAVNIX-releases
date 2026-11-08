// The layout of the desktop of RAVNIX.
//
// The panel is the panel of Plasma and the wallpaper is the plugin of the
// image, exactly as in the themes of KDE. The picture itself is set by the
// branding script, because the path of it is only known in the profile of the
// system.
loadTemplate("org.kde.plasma.desktop.defaultPanel");

var desktopsArray = desktopsForActivity(currentActivity());
for (var j = 0; j < desktopsArray.length; j++) {
    desktopsArray[j].wallpaperPlugin = 'org.kde.image';
}
