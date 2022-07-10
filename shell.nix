{ pkgs ? import <nixpkgs> {} }:
  pkgs.mkShell {
    nativeBuildInputs = [ 
      pkgs.buildPackages.gcc-arm-embedded-9
      pkgs.buildPackages.python39
      pkgs.openocd
      pkgs.stlink
      pkgs.SDL2
    ];
    hardeningDisable = ["all"];
}
