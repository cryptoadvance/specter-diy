{ pkgs ? import (fetchTarball {
    url = "https://github.com/NixOS/nixpkgs/archive/nixos-22.05.tar.gz";
    sha256 = "154x9swf494mqwi4z8nbq2f0sp8pwp4fvx51lqzindjfbb9yxxv5";
  }) {}
}:
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
