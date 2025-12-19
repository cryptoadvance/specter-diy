{
  description = "Specter DIY development environment";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
      in
      {
        devShells.default = pkgs.mkShell {
          nativeBuildInputs = [
            pkgs.buildPackages.gcc-arm-embedded
            pkgs.buildPackages.python3
            pkgs.openocd
            pkgs.gdb
            pkgs.SDL2
            # Serial terminal tools
            pkgs.minicom
            pkgs.screen
            pkgs.picocom
          ] ++ pkgs.lib.optionals pkgs.stdenv.isLinux [
            pkgs.stlink
          ];
          hardeningDisable = ["all"];
          shellHook = ''
            # Workaround for nixpkgs xcrun warnings on Darwin
            # See: https://github.com/NixOS/nixpkgs/issues/376958
            unset DEVELOPER_DIR
          '';
        };
      });
}
