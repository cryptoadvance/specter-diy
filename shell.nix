{ pkgs ? import <nixpkgs> {} }:
  pkgs.mkShell {
    nativeBuildInputs = [
      pkgs.buildPackages.gcc-arm-embedded-14
      pkgs.buildPackages.python3
      pkgs.openocd
      pkgs.stlink
      pkgs.gdb
      pkgs.SDL2
    ];
    hardeningDisable = ["all"];
}
