#!/usr/bin/env bash
# Commander Rescue — update an existing stick in place. Never erases anything
# except old versions of the tools this project put there.
#
#   ./refresh.sh                 find the plugged-in Ventoy stick and update it
#   ./refresh.sh --upgrade-ventoy  also update the Ventoy boot loader itself
set -Eeuo pipefail
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/common.sh
source "$HERE/scripts/common.sh"
trap on_err ERR
CRESCUE="$HERE/crescue"

usage() {
  cat <<EOF
Usage: ./refresh.sh [options] [/dev/sdX1 | /mount/point]

Checks upstream for new releases, downloads + verifies them, and swaps them
onto your Ventoy stick. Files you added yourself are left alone.

Options:
  --upgrade-ventoy   also upgrade Ventoy on the stick (non-destructive, needs sudo)
  --skip-fetch       only sync what's already cached
  --verify           re-hash every file on the stick after copying (slow)
  --dry-run          show what would change
  --eject            unmount when finished
  -h, --help         this help
EOF
}

upgrade=0 skip_fetch=0 eject=0 target='' sync_args=()
while (($#)); do
  case $1 in
    --upgrade-ventoy) upgrade=1 ;;
    --skip-fetch) skip_fetch=1 ;;
    --verify) sync_args+=(--verify) ;;
    --dry-run) sync_args+=(--dry-run) ;;
    --eject) eject=1 ;;
    -h|--help) usage; exit 0 ;;
    -*) usage; die "unknown option: $1" ;;
    *) target=$1 ;;
  esac
  shift
done

[[ $EUID -ne 0 ]] || die "run this as your normal user"
check_python
need lsblk util-linux
need findmnt util-linux

# ── Find the stick ───────────────────────────────────────────────────────
part=''
if [[ -d $target ]]; then
  mnt=$target
  part=$(findmnt -no SOURCE --target "$mnt" || true)
else
  if [[ -b $target ]]; then
    part=$target
  else
    mapfile -t found < <(lsblk -lnpo NAME,LABEL | awk '$2=="Ventoy"{print $1}')
    ((${#found[@]})) || die "no Ventoy stick found. Plug it in, or pass its partition / mount point."
    ((${#found[@]} == 1)) || die "more than one Ventoy stick plugged in (${found[*]}) — pass the one you want"
    part=${found[0]}
  fi
  mnt=$(mount_part "$part")
fi
[[ -n $mnt ]] || die "couldn't mount the stick"
ok "Stick: ${part:-?} at $mnt"

# ── Ventoy upgrade (optional) ────────────────────────────────────────────
if ((upgrade)); then
  need sudo
  "$CRESCUE" fetch ventoy
  vdir=$("$CRESCUE" ventoy-path)
  disk=/dev/$(lsblk -no PKNAME "$part" | head -n1)
  [[ -b $disk ]] || die "can't work out which disk $part is on"
  head "Upgrading Ventoy on $disk (your files are kept)"
  unmount_part "$part"
  (cd "$vdir" && printf 'y\n' | sudo ./Ventoy2Disk.sh -u "$disk")
  sudo udevadm settle 2>/dev/null || sleep 3
  mnt=$(mount_part "$part")
fi

# ── Fetch + sync ─────────────────────────────────────────────────────────
if ! ((skip_fetch)); then
  "$CRESCUE" fetch || warn "some downloads failed — syncing everything else"
fi
"$CRESCUE" sync "$mnt" "${sync_args[@]}"

if ((eject)) && [[ -n $part ]]; then
  unmount_part "$part"
  ok "Unmounted — safe to unplug."
fi
