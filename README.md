# Photo Terminal

Pick photos in the terminal, shrink them, and upload them to S3.

## First-time setup

Install [Nix](https://nixos.org/download/) and [direnv](https://direnv.net/), then enable direnv in your shell. For zsh, add this to `~/.zshrc`:

```sh
eval "$(direnv hook zsh)"
```

Then:

```sh
cd photo-terminal
direnv allow
cp .env.example .env
```

Put your AWS keys in `.env`. That is it. From now on, `cd` into this folder and direnv will install/load everything automatically. You do **not** need to activate Python.

## Use it

```sh
pt <photo-or-folder>
```

Examples:

```sh
pt ~/Desktop/photo.jpg
pt ~/Desktop/trip-photos
```

The upload location is entered as a stage in the workflow, just before the final upload review. Press Enter to complete each stage and to submit the final upload.

The S3 bucket and target image size live in `photo-uploader.yaml`. The app creates that file the first time it runs.

Use `pt --help` for the few extra options, including `--dry-run`.

## If `pt` is not found

Run `direnv allow` once. If it still does not load when you `cd` here, your shell is missing the direnv hook shown above.
