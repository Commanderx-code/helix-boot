# shellcheck shell=bash
# Shared helpers for install.sh / refresh.sh. Sourced, not executed.

if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
  G=$'\e[32m' Y=$'\e[33m' R=$'\e[31m' B=$'\e[1m' D=$'\e[2m' X=$'\e[0m'
else
  G='' Y='' R='' B='' D='' X=''
fi

# The Helix Boot logo: ANSI Shadow letters, purple to cyan like the Helix Neon theme. Plain
# text instead on a terminal that can't show it (not UTF-8, or under 76 columns).
banner() {  # banner <what this run does>
  [[ -z ${HELIX_NO_BANNER:-} ]] || return 0   # HelixBoot.sh's menu already showed it
  local what=$1 cols ver='' r i
  cols=$(tput cols 2>/dev/null) || cols=80
  if [[ -n ${HELIX:-} ]]; then ver=$("$HELIX" --version 2>/dev/null) || ver=''; fi
  local charset=${LC_ALL:-${LC_CTYPE:-${LANG:-}}}
  if [[ $charset != *[Uu][Tt][Ff]* ]] || ((cols < 76)); then
    printf '\n%sHELIX BOOT%s  %s%s%s  %s\n\n' "$B" "$X" "$D" "$what" "$X" "$ver"
    return
  fi
  local -a rows=(
    '██╗  ██╗███████╗██╗     ██╗██╗  ██╗  ██████╗  ██████╗  ██████╗ ████████╗'
    '██║  ██║██╔════╝██║     ██║╚██╗██╔╝  ██╔══██╗██╔═══██╗██╔═══██╗╚══██╔══╝'
    '███████║█████╗  ██║     ██║ ╚███╔╝   ██████╔╝██║   ██║██║   ██║   ██║   '
    '██╔══██║██╔══╝  ██║     ██║ ██╔██╗   ██╔══██╗██║   ██║██║   ██║   ██║   '
    '██║  ██║███████╗███████╗██║██╔╝ ██╗  ██████╔╝╚██████╔╝╚██████╔╝   ██║   '
    '╚═╝  ╚═╝╚══════╝╚══════╝╚═╝╚═╝  ╚═╝  ╚═════╝  ╚═════╝  ╚═════╝    ╚═╝   '
  )
  local -a at=(0 8 16 24 27 37 45 54 63) wide=(8 8 8 3 10 8 9 9 9)   # each letter (X takes the gap)
  local -a shade=(99 135 141 147 111 75 81 45 51)
  printf '\n'
  for r in "${rows[@]}"; do
    printf '  '
    for i in "${!at[@]}"; do
      if [[ -n $X ]]; then printf '\e[38;5;%sm%s' "${shade[$i]}" "${r:${at[$i]}:${wide[$i]}}"
      else printf '%s' "${r:${at[$i]}:${wide[$i]}}"; fi
    done
    printf '%s\n' "$X"
  done
  printf '  %s        RECOVERY  •  DIAGNOSTICS  •  REPAIR        %s%s%s\n\n' "$D" "$X" "$B" "$what${ver:+  ·  $ver}$X"
}

ok()   { printf '%s✓%s %s\n' "$G" "$X" "$*"; }
warn() { printf '%s!%s %s\n' "$Y" "$X" "$*"; }
info() { printf '%s•%s %s\n' "$D" "$X" "$*"; }
section() { printf '\n%s%s%s\n' "$B" "$*" "$X"; }
die()  { printf '%s✗%s %s\n' "$R" "$X" "$*" >&2; exit 1; }

# Friendly failure instead of a bare exit code.
on_err() {
  local code=$? cmd=$BASH_COMMAND
  if [[ $cmd == *HELIX* || $cmd == *bundled_pack* ]]; then
    :  # helix (or die) already explained what went wrong
  elif [[ $code -eq 127 ]]; then
    printf '%s✗%s command not found: %s\n' "$R" "$X" "${cmd%% *}" >&2
  else
    printf '%s✗%s this step failed: %s\n' "$R" "$X" "$cmd" >&2
  fi
  exit "$code"
}

pkg_hint() {
  local pkg=$1
  if command -v pacman >/dev/null; then echo "sudo pacman -S $pkg"
  elif command -v apt >/dev/null; then echo "sudo apt install $pkg"
  elif command -v dnf >/dev/null; then echo "sudo dnf install $pkg"
  else echo "install '$pkg' with your package manager"; fi
}

need() {  # need <command> [package]
  command -v "$1" >/dev/null || die "missing '$1' — $(pkg_hint "${2:-$1}")"
}

check_python() {
  need python3 python
  python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' \
    || die "Python 3.11+ is required (found $(python3 -V 2>&1))"
}

# Every member of a mounted Btrfs filesystem, including devices hidden by findmnt's
# single SOURCE. sysfs exposes these without requiring root or btrfs-progs.
btrfs_devices() {
  local uuid=$1 entry number found=0
  [[ $uuid =~ ^[0-9a-fA-F-]{36}$ ]] || return 1
  for entry in /sys/fs/btrfs/"$uuid"/devices/*; do
    number=$(cat "$entry/dev") || return 1
    [[ $number =~ ^[0-9]+:[0-9]+$ ]] || return 1
    printf '/dev/block/%s\n' "$number"
    found=1
  done
  ((found))
}

mount_devices() {
  local row src type uuid
  row=$(findmnt -nro SOURCE,FSTYPE,UUID --target "$1") || return 1
  read -r src type uuid <<< "$row"
  [[ -n $src && -n $type ]] || return 1
  if [[ $type == btrfs ]]; then
    btrfs_devices "$uuid" || return 1
  else
    src=${src%%\[*}             # subvolume / bind-mount suffix
    if [[ $src == /dev/* ]]; then printf '%s\n' "$src"; fi
  fi
}

# Whole disks that hold the running system (/, /boot, /home, swap …), through LUKS/LVM/btrfs.
# Emit nothing until every lookup succeeds, so callers cannot consume a partial list.
system_disks() {
  local m src devices swaps ancestors disk type
  local -a sources=() disks=()
  for m in / /boot /boot/efi /efi /home /usr /var; do
    [[ -e $m ]] || continue
    devices=$(mount_devices "$m") || return 1
    while IFS= read -r src; do [[ -z $src ]] || sources+=("$src"); done <<< "$devices"
  done
  swaps=$(swapon --noheadings --raw --show=NAME) || return 1
  while IFS= read -r src; do
    [[ -n $src ]] || continue
    if [[ $src == /dev/* ]]; then
      sources+=("$src")
    else
      devices=$(mount_devices "$src") || return 1  # swap file on a separate filesystem
      while IFS= read -r src; do [[ -z $src ]] || sources+=("$src"); done <<< "$devices"
    fi
  done <<< "$swaps"
  for src in "${sources[@]}"; do
    ancestors=$(lsblk -lnspo NAME,TYPE "$src") || return 1
    [[ -n $ancestors ]] || return 1
    while read -r disk type; do
      [[ $type != disk ]] || disks+=("$disk")
    done <<< "$ancestors"
  done
  if ((${#disks[@]})); then printf '%s\n' "${disks[@]}" | sort -u; fi
}

# Removable / USB whole disks as "PATH<TAB>SIZE<TAB>MODEL".
usb_disks() {
  lsblk -Jdpo PATH,SIZE,MODEL,TRAN,RM,TYPE | python3 -c '
import json, sys
for d in json.load(sys.stdin)["blockdevices"]:
    if d["type"] == "disk" and (d.get("tran") == "usb" or d.get("rm") in (True, "1")):
        print(d["path"], d.get("size") or "?", (d.get("model") or "").strip() or "unknown", sep="\t")
'
}

# What Ventoy says is on a disk, as "VERSION<TAB>YES|NO" (Secure Boot), or
# nothing if the disk has no Ventoy. Ventoy2Disk.sh exits 0 even when it bails
# out at a prompt, so this is how we know an install/upgrade really happened.
ventoy_info() {  # ventoy_info <ventoy dir> <disk>
  { (cd "$1" && sudo ./Ventoy2Disk.sh -l "$2") 2>/dev/null || true; } | awk -F': *' '
    /^Ventoy Version in Disk/ {v = $2}
    /^Secure Boot Support/    {s = $2}
    END { if (v != "") print v "\t" s }'
}

first_partition() {
  lsblk -lnpo NAME,TYPE "$1" | awk '$2=="part"{print $1; exit}'
}

# Mount a partition as the current user and print the mount point.
# Helix Boot's splash before the Ventoy menu, and what the L and F1 keys do: `helix splash` adds
# both to Ventoy's own boot script on the VTOYEFI partition. Given the stick's data partition
# (mounted), its menu is told, so its hotkey row shows what the keys really do. Never fails the
# run: without it, Ventoy starts as usual.
apply_splash() {  # apply_splash <disk> [mount point of its data partition]
  local efi efi_mnt
  local -a stick=()
  if [[ -n ${2:-} && -d $2 ]]; then stick=(--stick "$2"); fi
  efi=$(lsblk -lnpo NAME,LABEL "$1" 2>/dev/null | awk '$2=="VTOYEFI" { print $1; exit }') || efi=''
  if [[ -z $efi ]]; then warn "no VTOYEFI partition on ${1:-that disk}, so no splash"; return 0; fi
  efi_mnt=$(mount_part "$efi" 2>/dev/null) || efi_mnt=''
  if [[ -z $efi_mnt ]]; then warn "couldn't mount $efi, so no splash"; return 0; fi
  "$HELIX" splash "$efi_mnt" "${stick[@]}" || warn "couldn't add the splash; Ventoy starts without it"
  unmount_part "$efi" 2>/dev/null || true
}

# Find the Ventoy stick: the one plugged in, or the partition / mount point given. Sets $part
# and $mnt (mounting it if it isn't). A stick is known by Ventoy's own small partition, always
# labelled VTOYEFI: the data partition before it may have been renamed.
find_stick() {  # find_stick [/dev/sdX1 | /mount/point]
  local target=${1:-} found
  [[ -z $target || -d $target || -b $target ]] || die "target does not exist or is not a folder/block device: $target"
  part=''
  if [[ -d $target ]]; then
    mnt=$target
    part=$(findmnt -no SOURCE --target "$mnt" || true)
  else
    if [[ -b $target ]]; then
      part=$target
    else
      mapfile -t found < <(lsblk -lnpo PKNAME,LABEL | awk '$2=="VTOYEFI"{print $1}' | sort -u |
                           while read -r disk; do first_partition "$disk"; done)
      ((${#found[@]})) || die "no Ventoy stick found. Plug it in, or pass its partition / mount point."
      ((${#found[@]} == 1)) || die "more than one Ventoy stick plugged in (${found[*]}) — pass the one you want"
      part=${found[0]}
    fi
    mnt=$(mount_part "$part")
  fi
  [[ -n $mnt ]] || die "couldn't mount the stick"
  ok "Stick: ${part:-?} at $mnt"
}

mount_part() {
  local part=$1 mnt
  mnt=$(findmnt -no TARGET "$part" 2>/dev/null | head -n1 || true)
  if [[ -n $mnt ]]; then echo "$mnt"; return; fi
  if command -v udisksctl >/dev/null; then
    udisksctl mount -b "$part" >/dev/null
  else
    mnt=$(mktemp -d /tmp/helix-boot.XXXX)
    sudo mount -o "uid=$(id -u),gid=$(id -g)" "$part" "$mnt"
  fi
  findmnt -no TARGET "$part" | head -n1
}

unmount_part() {
  local part=$1
  findmnt -no TARGET "$part" >/dev/null 2>&1 || return 0
  if command -v udisksctl >/dev/null; then
    udisksctl unmount -b "$part" >/dev/null
  else
    sudo umount "$part"
  fi
}

# Inside a pack's installer/ folder (unzipped from the pack), the pack is the zip
# beside that folder. Prints its path, or nothing when not running from a pack.
bundled_pack() {  # bundled_pack <script dir>
  [[ -f $1/.bundled ]] || return 0
  local packs=() z
  for z in "$1"/../*.zip; do
    [[ -f $z ]] && { unzip_has "$z" helix-boot-pack.json || unzip_has "$z" commander-rescue-pack.json; } \
      && packs+=("$(realpath -- "$z")")
  done
  ((${#packs[@]})) || die "can't find the pack beside $(realpath -- "$1"). Pass it with --from /path/to/pack.zip"
  ((${#packs[@]} == 1)) || die "more than one pack beside $(realpath -- "$1") — pass the one you want with --from"
  echo "${packs[0]}"
}

unzip_has() {  # unzip_has <zip> <member>: is that file in the zip?
  python3 -c 'import sys, zipfile
try:
    sys.exit(sys.argv[2] not in zipfile.ZipFile(sys.argv[1]).namelist())
except (OSError, zipfile.BadZipFile):
    sys.exit(1)' "$1" "$2"
}

# DISKSEQ changes when a device is unplugged/replaced, even when /dev/sdX is reused.
# Refuse older kernels without it: a name or size alone cannot bind an erase confirmation.
disk_identity() {
  local dev seq
  dev=$(readlink -f -- "$1")
  seq=$(cat "/sys/class/block/${dev##*/}/diskseq") || return 1
  [[ $seq =~ ^[0-9]+$ ]] || return 1
  printf '%s:%s:%s\n' "$dev" "$seq" "$(lsblk -bdno SIZE "$dev")"
}

check_disk_identity() {
  local current disk protected
  current=$(disk_identity "$1") || die "cannot establish disk identity for $1; refusing to write"
  [[ $current == "$2" ]] || die "$1 was disconnected or replaced; select and confirm it again"
  protected=$(system_disks) || die "cannot determine the system disks; refusing to write"
  while read -r disk; do
    [[ $disk != "$1" ]] || die "$1 now holds the running system; refusing to write"
  done <<< "$protected"
  usb_disks | cut -f1 | grep -Fxq -- "$1" || die "$1 is no longer a USB/removable disk"
}
