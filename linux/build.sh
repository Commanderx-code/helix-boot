#!/usr/bin/env bash
# Build dist/HelixBoot.sh: linux/HelixBoot.sh.in with everything install.sh and refresh.sh
# need packed on behind it (a gzipped tar of the tracked files, byte-for-byte reproducible).
#
#   linux/build.sh [output]      default: dist/HelixBoot.sh
set -Eeuo pipefail
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO=$(cd -- "$HERE/.." && pwd)
# shellcheck source=scripts/common.sh
source "$REPO/scripts/common.sh"
trap on_err ERR

out=${1:-$REPO/dist/HelixBoot.sh}
need git
need tar
need gzip
need sha256sum coreutils

version=$("$REPO/helix" --version)
version=${version##* }
# What install.sh, refresh.sh and helix use on a stick: no build scripts, no docs, nothing untracked.
mapfile -t files < <(git -C "$REPO" ls-files -- \
  helix tools.toml install.sh refresh.sh theme.sh check.sh scripts/common.sh LICENSE local.toml.example byo/README.md \
  theme pe/launcher pe/lazarus portableapps/themes portableapps/settings | grep -v '\.py$')
((${#files[@]})) || die "no files to pack (run this from a git checkout)"

work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
tar -C "$REPO" --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - -- "${files[@]}" \
  | gzip -9n >"$work/payload.tar.gz"
sha=$(sha256sum "$work/payload.tar.gz")
sha=${sha%% *}

mkdir -p -- "$(dirname -- "$out")"
sed -e "s/@VERSION@/$version/" -e "s/@SHA256@/$sha/" "$HERE/HelixBoot.sh.in" >"$work/HelixBoot.sh"
printf '__HELIX_BOOT_PAYLOAD__\n' >>"$work/HelixBoot.sh"
cat "$work/payload.tar.gz" >>"$work/HelixBoot.sh"
chmod 755 "$work/HelixBoot.sh"
mv -- "$work/HelixBoot.sh" "$out"
ok "$out: Helix Boot $version, ${#files[@]} files ($(du -h "$out" | cut -f1))"
