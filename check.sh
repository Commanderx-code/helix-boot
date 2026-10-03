#!/usr/bin/env bash
# Read your Helix Boot stick back and find damaged or missing files. Cheap sticks go bad
# quietly; this compares every boot image and app with what was put on the stick, so it
# needs no downloads. What it finds damaged, the next refresh copies again.
#   ./check.sh                 the stick that's plugged in
#   ./check.sh --stick /dev/sdb1
set -Eeuo pipefail
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/common.sh
source "$HERE/scripts/common.sh"
trap on_err ERR
HELIX="$HERE/helix"

usage() {
  cat <<EOF
Usage: ./check.sh [options]

Reads the whole stick, so it takes a while (about as long as copying it).

Options:
  --stick WHERE   the stick's partition or mount point, if more than one is plugged in
  --eject         unmount when finished
  -h, --help      this help
EOF
}

eject=0 target=''
while (($#)); do
  case $1 in
    --stick) target=${2:?--stick needs a partition or mount point}; shift ;;
    --eject) eject=1 ;;
    -h|--help) usage; exit 0 ;;
    *) usage; die "unknown option: $1" ;;
  esac
  shift
done

banner "check"
[[ $EUID -ne 0 ]] || die "run this as your normal user"
check_python
need lsblk util-linux
need findmnt util-linux
find_stick "$target"
rc=0
"$HELIX" verify "$mnt" || rc=$?

if ((eject)) && [[ -n $part ]]; then
  unmount_part "$part"
  ok "Unmounted — safe to unplug."
fi
exit "$rc"
