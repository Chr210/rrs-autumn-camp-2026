{
  description = "Development environment for RoboCup RRS autumn camp 2026";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [ "aarch64-darwin" "x86_64-darwin" "aarch64-linux" "x86_64-linux" ];
    in {
      devShells = nixpkgs.lib.genAttrs systems (system:
        let pkgs = import nixpkgs { inherit system; };
        in {
          default = pkgs.mkShell {
            packages = with pkgs; [ bash git jdk21 python313 uv curl unzip ];
            JAVA_HOME = "${pkgs.jdk21}";
            UV_PYTHON_DOWNLOADS = "never";
          };
        });
    };
}
