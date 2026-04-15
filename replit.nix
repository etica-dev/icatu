{pkgs}: {
  deps = [
    pkgs.chromium
    pkgs.libGL
    pkgs.eudev
    pkgs.glib
    pkgs.xorg.libxcb
    pkgs.xorg.libXrandr
    pkgs.xorg.libXfixes
    pkgs.xorg.libXext
    pkgs.xorg.libXdamage
    pkgs.xorg.libXcomposite
    pkgs.xorg.libX11
    pkgs.pango
    pkgs.mesa
    pkgs.libxkbcommon
    pkgs.libdrm
    pkgs.expat
    pkgs.dbus
    pkgs.cups
    pkgs.atk
    pkgs.alsa-lib
    pkgs.nss
    pkgs.nspr
  ];
}
