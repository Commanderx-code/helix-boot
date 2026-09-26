# shellcheck shell=bash
# Shared helpers for install.sh / refresh.sh. Sourced, not executed.

if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
  G=$'\e[32m' Y=$'\e[33m' R=$'\e[31m' B=$'\e[1m' D=$'\e[2m' X=$'\e[0m'
else
  G='' Y='' R='' B='' D='' X=''
fi

ok()   { printf '%s✓%s %s\n' "$G" "$X" "$*"; }
warn() { printf '%s!%s %s\n' "$Y" "$X" "$*"; }
info() { printf '%s•%s %s\n' "$D" "$X" "$*"; }
head() { printf '\n%s%s%s\n' "$B" "$*" "$X"; }
die()  { printf '%s✗%s %s\n' "$R" "$X" "$*" >&2; exit 1; }

# Friendly failure instead of a bare exit code.
on_err() {
  local code=$? cmd=$BASH_COMMAND
  if [[ $cmd == *CRESCUE* ]]; then
    :  # crescue already explained what went wrong
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

first_partition() {
  lsblk -lnpo NAME,TYPE "$1" | awk '$2=="part"{print $1; exit}'
}

# Mount a partition as the current user and print the mount point.
mount_part() {
  local part=$1 mnt
  mnt=$(findmnt -no TARGET "$part" 2>/dev/null | head -n1 || true)
  if [[ -n $mnt ]]; then echo "$mnt"; return; fi
  if command -v udisksctl >/dev/null; then
    udisksctl mount -b "$part" >/dev/null
  else
    mnt=$(mktemp -d /tmp/commander-rescue.XXXX)
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
