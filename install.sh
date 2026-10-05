#!/usr/bin/env bash
# Helix Boot — build a fresh stick.
#
#   ./install.sh                 pick a USB stick interactively
#   ./install.sh /dev/sdX        use that stick
#   ./install.sh --from pack.zip  fill it from a pack (`helix pack`), no downloads
#
# Everything is downloaded and verified BEFORE the stick is touched, and you
# must type the device name to confirm the wipe.
set -Eeuo pipefail
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/common.sh
source "$HERE/scripts/common.sh"
trap on_err ERR
HELIX="$HERE/helix"

usage() {
  cat <<EOF
Usage: ./install.sh [options] [/dev/sdX]

Installs Ventoy on a USB stick (ERASING it) and fills it with the tools
from tools.toml.

Options:
  --mbr              MBR partition table instead of GPT (very old BIOS machines)
  --no-secure-boot   don't add Ventoy's Secure Boot shim
  --reserve MB       leave MB of unallocated space at the end of the stick
  --skip-fetch       use what's already cached; don't check upstream
  --test             test the stick before filling it: write it full and read it
                     back (slow). A failing or fake stick is found now, not later
  --from PACK        use a pack made by "helix pack" instead of downloading
  --list             just list USB sticks and exit
  -h, --help         this help
EOF
}

gpt=1 secure=1 reserve='' skip_fetch=0 dev='' list_only=0 from='' test=0

show_sticks() {
  local i p s m
  for i in "${!sticks[@]}"; do
    IFS=$'\t' read -r p s m <<<"${sticks[$i]}"
    printf '  %s%d)%s %-14s %8s  %s\n' "$B" $((i + 1)) "$X" "$p" "$s" "$m"
  done
}
while (($#)); do
  case $1 in
    --mbr) gpt=0 ;;
    --no-secure-boot) secure=0 ;;
    --reserve) reserve=${2:?--reserve needs a size in MB}; shift ;;
    --skip-fetch) skip_fetch=1 ;;
    --test) test=1 ;;
    --from) from=${2:?--from needs a pack .zip}; shift ;;
    --list) list_only=1 ;;
    -h|--help) usage; exit 0 ;;
    /dev/*) dev=$1 ;;
    *) usage; die "unknown option: $1" ;;
  esac
  shift
done

((list_only)) || banner "install"
check_python
[[ -n $from ]] || from=$(bundled_pack "$HERE")
need lsblk util-linux
need findmnt util-linux
if ((list_only)); then
  mapfile -t sticks < <(usb_disks)
  if ((${#sticks[@]})); then show_sticks; else info "no USB sticks found"; fi
  exit 0
fi
[[ $EUID -ne 0 ]] || die "run this as your normal user — it asks for sudo only for the Ventoy step"
need sudo
((gpt)) && need parted  # Ventoy can only make GPT sticks with parted

# ── 1. Download + verify everything first ────────────────────────────────
if [[ -n $from ]]; then
  [[ -f $from ]] || die "can't find the pack $from"
  from=$(realpath -- "$from")
  info "using the pack $from (no downloads)"
elif ((skip_fetch)); then
  "$HELIX" ventoy-path >/dev/null 2>&1 || "$HELIX" fetch ventoy
else
  if ! "$HELIX" fetch; then
    warn "some tools failed to download (listed above)."
    read -rp "Continue with what was fetched? [y/N] " a
    [[ ${a,,} == y* ]] || die "stopped — nothing was written to any disk"
  fi
fi
if [[ -n $from ]]; then vdir=$("$HELIX" ventoy-path --from "$from"); else vdir=$("$HELIX" ventoy-path); fi

# ── 2. Pick the stick ────────────────────────────────────────────────────
mapfile -t sticks < <(usb_disks)
protected_list=$(system_disks) || die "cannot determine the system disks; refusing to install"
mapfile -t protected <<< "$protected_list"

if [[ -z $dev ]]; then
  ((${#sticks[@]})) || die "no USB sticks found. Plug one in, or pass the device path."
  section "USB sticks"
  show_sticks
  read -rp "Which one? [1-${#sticks[@]}] " n
  if ! [[ $n =~ ^[0-9]+$ ]] || ((n < 1 || n > ${#sticks[@]})); then die "not a choice: $n"; fi
  dev=${sticks[$((n - 1))]%%$'\t'*}
fi

dev=$(readlink -f -- "$dev")
[[ -b $dev ]] || die "$dev isn't a block device"
[[ $(lsblk -dno TYPE "$dev") == disk ]] || die "$dev is a partition — pass the whole disk (e.g. /dev/sdb)"
for p in "${protected[@]}"; do
  [[ $p == "$dev" ]] && die "$dev holds your running system. Refusing."
done
is_usb=0
for s in "${sticks[@]}"; do [[ ${s%%$'\t'*} == "$dev" ]] && is_usb=1; done
((is_usb)) || die "$dev isn't a USB/removable disk. Refusing (edit install.sh if you really mean it)."

identity=$(disk_identity "$dev") || die "cannot establish disk identity; refusing to erase"

# ── 3. Confirm ───────────────────────────────────────────────────────────
section "This will ERASE everything on:"
lsblk -o NAME,SIZE,FSTYPE,LABEL,MOUNTPOINTS "$dev" | sed 's/^/  /'
echo
bytes=$(lsblk -bdno SIZE "$dev")
((bytes < 300 * 1000 ** 3)) || warn "$dev is $(lsblk -dno SIZE "$dev") — bigger than most sticks. Is this an external drive with your backups on it?"
read -rp "Type ${B}$(basename "$dev")${X} to erase it: " typed
[[ $typed == "$(basename "$dev")" ]] || die "didn't match — nothing was changed"

# ── 4. Ventoy ────────────────────────────────────────────────────────────
check_disk_identity "$dev" "$identity"
while read -r part; do
  [[ -n $part ]] && unmount_part "$part"
done < <(lsblk -lnpo NAME,TYPE "$dev" | awk '$2=="part"{print $1}')

flags=(-I)
label=$("$HELIX" setting stick_label)     # the stick's name; Ventoy's own is "Ventoy"
[[ $label == Ventoy ]] || flags+=(-L "$label")
((gpt)) && flags+=(-g)
if ((secure)); then flags+=(-s); else flags+=(-S); fi
[[ -n $reserve ]] && flags+=(-r "$reserve")

want=$(basename "$vdir" | sed 's/^ventoy-//')
section "Installing Ventoy $want"
# Ventoy2Disk.sh asks "Continue?" twice; we've already confirmed above.
check_disk_identity "$dev" "$identity"
(cd "$vdir" && printf 'y\ny\n' | sudo ./Ventoy2Disk.sh "${flags[@]}" "$dev")
sudo udevadm settle 2>/dev/null || sleep 3
check_disk_identity "$dev" "$identity"
got=$(ventoy_info "$vdir" "$dev")
[[ ${got%%$'\t'*} == "$want" ]] || die "Ventoy didn't install on $dev — see $vdir/log.txt"

check_disk_identity "$dev" "$identity"
part=$(first_partition "$dev")
[[ -n $part ]] || die "can't find the Ventoy data partition on $dev"
mnt=$(mount_part "$part")
[[ -n $mnt ]] || die "couldn't mount $part"
ok "Ventoy installed, data partition mounted at $mnt"

check_disk_identity "$dev" "$identity"
if ((test)); then
  "$HELIX" test "$mnt" || die "this stick failed the test: it is left empty. Use another stick."
  check_disk_identity "$dev" "$identity"
fi
# ── 5. Fill it ───────────────────────────────────────────────────────────
if [[ -n $from ]]; then
  "$HELIX" unpack "$from" "$mnt" --init --verify
else
  "$HELIX" sync "$mnt" --init --verify
fi

check_disk_identity "$dev" "$identity"
section "Finishing"
apply_splash "$dev" "$mnt"
unmount_part "$part"
ok "Done. You can unplug the stick."
((secure)) && info "First boot on a Secure Boot PC: pick 'Enroll key' → ENROLL_THIS_KEY_IN_MOKMANAGER.cer, then reboot."
info "Refresh it later with ./refresh.sh"
