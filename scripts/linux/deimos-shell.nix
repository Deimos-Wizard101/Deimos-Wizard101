# Native-Linux Deimos runtime libs. nix-shell sets LD_LIBRARY_PATH without a
# sandbox, so the pip wheels (Qt/numpy/shapely/keystone) find their native libs
# AND the process can read the game client's /proc/<pid>/mem (steam-run's user
# namespace blocks that cross-process access).
{ pkgs ? import <nixpkgs> { } }:
let
  libs = with pkgs; [
    stdenv.cc.cc.lib libxkbcommon fontconfig freetype dbus zlib glib libGL libffi
    wayland expat libxml2 zstd libpng util-linux.lib
    xorg.libX11 xorg.libxcb xorg.libXau xorg.libXdmcp xorg.libXext xorg.libXrender
    xorg.libXi xorg.libXrandr xorg.libXfixes xorg.libXcursor xorg.libXcomposite
    xorg.libXdamage xorg.libXtst xorg.libSM xorg.libICE xorg.libxkbfile
    xorg.xcbutil xorg.xcbutilwm xorg.xcbutilimage xorg.xcbutilkeysyms xorg.xcbutilrenderutil xorg.xcbutilcursor
  ];
in
pkgs.mkShell {
  packages = [ pkgs.xdotool ];
  shellHook = ''
    export LD_LIBRARY_PATH=${pkgs.lib.makeLibraryPath libs}:/run/opengl-driver/lib''${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
  '';
}
