#!/usr/bin/env bash
# Helix Boot — update an existing stick in place. Never erases anything
# except old versions of the tools this project put there.
#
#   ./refresh.sh                 find the plugged-in Ventoy stick and update it
#   ./refresh.sh --upgrade-ventoy  also update the Ventoy boot loader itself
#   ./refresh.sh --from pack.zip   update it from a pack (`helix pack`), no downloads
set -Eeuo pipefail
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/common.sh
source "$HERE/scripts/common.sh"
trap on_err ERR
HELIX="$HERE/helix"

usage() {
  cat <<EOF
Usage: ./refresh.sh [options] [/dev/sdX1 | /mount/point]

Checks upstream for new releases, downloads + verifies them, and swaps them
onto your Ventoy stick. Files you added yourself are left alone.

Options:
  --upgrade-ventoy   also upgrade Ventoy on the stick (non-destructive, needs sudo)
  --skip-fetch       only sync what's already cached
  --from PACK        update from a pack made by "helix pack" instead of downloading
  --verify           re-hash every file on the stick after copying (slow)
  --dry-run          show what would change
  --eject            unmount when finished
  -h, --help         this help
EOF
}

upgrade=0 skip_fetch=0 eject=0 target='' sync_args=() from=''
while (($#)); do
  case $1 in
    --upgrade-ventoy) upgrade=1 ;;
    --skip-fetch) skip_fetch=1 ;;
    --from) from=${2:?--from needs a pack .zip}; shift ;;
    --verify) sync_args+=(--verify) ;;
    --dry-run) sync_args+=(--dry-run) ;;
    --eject) eject=1 ;;
    -h|--help) usage; exit 0 ;;
    -*) usage; die "unknown option: $1" ;;
    *) target=$1 ;;
  esac
  shift
done

banner "refresh"
[[ $EUID -ne 0 ]] || die "run this as your normal user"
check_python
[[ -n $from ]] || from=$(bundled_pack "$HERE")
if [[ -n $from ]]; then
  [[ -f $from ]] || die "can't find the pack $from"
  from=$(realpath -- "$from")
fi
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
  if [[ -n $from ]]; then
    vdir=$("$HELIX" ventoy-path --from "$from")
  else
    "$HELIX" fetch ventoy
    vdir=$("$HELIX" ventoy-path)
  fi
  disk=/dev/$(lsblk -no PKNAME "$part" | head -n1)
  [[ -b $disk ]] || die "can't work out which disk $part is on"
  want=$(basename "$vdir" | sed 's/^ventoy-//')
  unmount_part "$part"
  old=$(ventoy_info "$vdir" "$disk")
  [[ -n $old ]] || die "Ventoy can't find its install on $disk"
  if [[ ${old%%$'\t'*} == "$want" ]]; then
    ok "Ventoy is already $want"
  else
    section "Upgrading Ventoy ${old%%$'\t'*} → $want on $disk (your files are kept)"
    # -u turns Secure Boot support on unless told otherwise; keep the stick's setting.
    flags=(-u)
    [[ ${old#*$'\t'} == NO ]] && flags+=(-S)
    (cd "$vdir" && printf 'y\n' | sudo ./Ventoy2Disk.sh "${flags[@]}" "$disk")
    sudo udevadm settle 2>/dev/null || sleep 3
    got=$(ventoy_info "$vdir" "$disk")
    [[ ${got%%$'\t'*} == "$want" ]] || die "Ventoy upgrade on $disk didn't finish — see $vdir/log.txt"
    ok "Ventoy upgraded to $want"
  fi
  mnt=$(mount_part "$part")
fi

# ── Fetch + sync ─────────────────────────────────────────────────────────
if [[ -n $from ]]; then
  "$HELIX" unpack "$from" "$mnt" "${sync_args[@]}"
else
  if ! ((skip_fetch)); then
    "$HELIX" fetch || warn "some downloads failed — syncing everything else"
  fi
  "$HELIX" sync "$mnt" "${sync_args[@]}"
fi

# The splash before the Ventoy menu (again after a Ventoy upgrade, which replaces it)
if [[ -n $part && " ${sync_args[*]} " != *" --dry-run "* ]]; then
  apply_splash "/dev/$(lsblk -no PKNAME "$part" | head -n1)"
fi

if ((eject)) && [[ -n $part ]]; then
  unmount_part "$part"
  ok "Unmounted — safe to unplug."
fi
