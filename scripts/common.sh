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

# Whole disks that hold the running system (/, /boot, /home, swap …), through LUKS/LVM/btrfs.
system_disks() {
  local src
  {
    for m in / /boot /boot/efi /efi /home /usr /var; do
      findmnt -no SOURCE "$m" 2>/dev/null || true
    done
    swapon --noheadings --show=NAME 2>/dev/null || true
  } | sed 's/\[.*\]$//' | sort -u | while read -r src; do
    [[ $src == /dev/* ]] || continue
    lsblk -lnspo NAME,TYPE "$src" 2>/dev/null | awk '$2=="disk"{print $1}'
  done | sort -u
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
# Helix Boot's splash before the Ventoy menu: `helix splash` adds it to Ventoy's own boot
# script on the VTOYEFI partition. Never fails the run: without it, Ventoy starts as usual.
apply_splash() {  # apply_splash <disk>
  local efi mnt
  efi=$(lsblk -lnpo NAME,LABEL "$1" 2>/dev/null | awk '$2=="VTOYEFI" { print $1; exit }')
  if [[ -z $efi ]]; then warn "no VTOYEFI partition on $1, so no splash"; return 0; fi
  mnt=$(mount_part "$efi" 2>/dev/null) || mnt=''
  if [[ -z $mnt ]]; then warn "couldn't mount $efi, so no splash"; return 0; fi
  "$HELIX" splash "$mnt" || warn "couldn't add the splash; Ventoy starts without it"
  unmount_part "$efi" 2>/dev/null || true
}

# Find the Ventoy stick: the one plugged in, or the partition / mount point given. Sets $part
# and $mnt (mounting it if it isn't).
find_stick() {  # find_stick [/dev/sdX1 | /mount/point]
  local target=${1:-} found
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
