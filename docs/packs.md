# Packs: the whole stick in one file

Like MediCat's download, a pack is one file with every tool in it, ready to
extract onto a stick. It's made from your cache, so it includes your
bring-your-own tools and the Ventoy installer, and a new stick needs no internet:

```fish
./helix fetch                                 # bring everything up to date
./helix pack                                  # → helix-boot-<version>-<date>.zip
./install.sh --from helix-boot-<version>-<date>.zip # new stick
./refresh.sh --from helix-boot-<version>-<date>.zip # update a stick
```

`./helix pack --public` makes a pack you can share: only the tools anyone can
download, without your own files, your additions in `local.toml`, or your
icons and splash. `--split` also cuts a pack into 2 GiB pieces in a folder
beside it, with a checksum and a script that joins them, checks the result and
starts the installer: for uploading or sending one.

The pack carries its own installer, so on another Linux PC the zip is all you need:

```fish
unzip helix-boot-<version>-<date>.zip 'installer/*'   # a few MB
installer/install.sh                               # finds the zip beside it
```

On Windows, take `installer\HelixBoot.exe` out of the zip, keep it next to the
zip and run it: the window picks the pack up on its own (**Tools from: a pack**),
and Install or Update copy everything from it, Ventoy included, with no
downloads. A pack holds both Ventoy packages (Linux and Windows) and the
latest released `HelixBoot.exe`, each checked against its published checksum.

Inside is the stick exactly as `helix sync` lays it out, with boot images
stored uncompressed and each one's sha256 recorded: the boot images, the apps,
the Mac tools, every theme preset and your own icons and splash. Extracting
streams files straight onto the stick and checks every image, so a damaged pack
is caught, not booted. A stick filled from a pack refreshes normally
afterwards, keeps the look it had, and keeps tools the pack doesn't have
([why](engine.md#updating-from-more-than-one-pc)).

> [!IMPORTANT]
> A pack holds your licensed tools, so keep it private: a drive, a NAS or your
> own cloud storage, never a public repo or release. Packs made in this folder
> are git-ignored.
