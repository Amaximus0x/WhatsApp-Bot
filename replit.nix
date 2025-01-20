{ pkgs }: {
  deps = [
    pkgs.ffmpeg-full
    pkgs.python310
    pkgs.python310Packages.pip
    pkgs.python310Packages.setuptools
    pkgs.python310Packages.wheel
  ];
}