#!/usr/bin/env bash
# Show or change the look of your Helix Boot stick: its theme, icons, background and splash.
# The choice is kept on the stick, so a refresh doesn't undo it.
#   ./theme.sh                         how it looks now, and what there is to choose from
#   ./theme.sh --menu                  choose from numbered lists, with a preview
#   ./theme.sh --theme midnight        a preset theme (`off`: the plain one, Standby)
#   ./theme.sh --icons off             no icons (or `grey`, or an icon pack such as `badges`)
#   ./theme.sh --background pic.jpg --dim 40     your own picture behind the menu, darkened
#   ./theme.sh --splash pic.png        your own picture before the menu (`off`: none)
#   ./theme.sh --reset                 back to the default look
#   ./theme.sh --export my-look.zip    save the look, with your own pictures and icons
#   ./theme.sh --import my-look.zip    put a saved look on this stick (or another)
set -Eeuo pipefail
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/common.sh
source "$HERE/scripts/common.sh"
trap on_err ERR
HELIX="$HERE/helix"

usage() {
  cat <<EOF
Usage: ./theme.sh [options]

With no options: shows the stick's look and the themes and icon packs to choose from.

Options:
  --theme ID            a preset theme, or "default" ("off": the plain one, Standby)
  --icons ID            "auto" (the theme's own style, the default), "logos", "grey", an icon
                        pack such as "badges", or "off" for none
  --background PICTURE  your own picture behind the menu ("theme": the theme's again)
  --dim PERCENT         darken that picture (0-90) so the menu stays readable
  --splash PICTURE      your own picture before the menu ("theme", "auto", or "off")
  --reset               back to the default look
  --menu                choose from numbered lists instead, with a preview
  --preview FILE        don't change the stick: write a picture of how the menu would look
  --export ZIP          save the look, with your own pictures and icons, to a zip
  --import ZIP          put a saved look on the stick
  --stick WHERE         the stick's partition or mount point, if more than one is plugged in
  --eject               unmount when finished
  -h, --help            this help
EOF
}

eject=0 target='' args=()
while (($#)); do
  case $1 in
    --theme|--icons|--background|--dim|--splash|--preview|--export|--import) args+=("$1" "${2:?$1 needs a value}"); shift ;;
    --reset|--json|--menu) args+=("$1") ;;
    --stick) target=${2:?--stick needs a partition or mount point}; shift ;;
    --eject) eject=1 ;;
    -h|--help) usage; exit 0 ;;
    *) usage; die "unknown option: $1" ;;
  esac
  shift
done

[[ " ${args[*]} " == *" --json "* ]] || banner "theme"
[[ $EUID -ne 0 ]] || die "run this as your normal user"
check_python
need lsblk util-linux
need findmnt util-linux
if [[ " ${args[*]} " == *" --json "* ]]; then
  find_stick "$target" >/dev/null
else
  find_stick "$target"
fi
"$HELIX" theme "$mnt" "${args[@]}"

if ((eject)) && [[ -n $part ]]; then
  unmount_part "$part"
  ok "Unmounted — safe to unplug."
fi
