{
  description = "photo-terminal development environment";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/1f9a45d327c783996acc4690e83ff661fe1cf1b5"; # 2026-05-31
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
      in
      {
        devShells.default = pkgs.mkShell {
          packages = with pkgs; [
            python312
            uv
            awscli2
            viu
          ];

          shellHook = ''
            export UV_PROJECT_ENVIRONMENT="$PWD/.venv"
            export UV_NO_MANAGED_PYTHON=1
            uv sync --extra dev --frozen --python ${pkgs.python312}/bin/python --quiet
            export VIRTUAL_ENV="$UV_PROJECT_ENVIRONMENT"
            export PATH="$VIRTUAL_ENV/bin:$PATH"
          '';
        };
      }
    );
}
