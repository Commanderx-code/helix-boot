#!/usr/bin/env bash
# Helix Boot — give a PE ISO a newer Windows boot manager.
#
#   pe/fix-bootmgr.sh <windows.iso>            fix pe/out/LazarusPE.iso in place
#   pe/fix-bootmgr.sh <windows.iso> <pe.iso>   fix another PE ISO
#
# Why: Lazarus PE builds best from Windows 11 22H2/23H2, but those discs carry a
# 2022 UEFI boot manager that hangs on newer UEFI firmware, which enforces memory
# protections the old loader trips over. A newer boot manager starts the older PE
# just fine, so this copies the boot files (bootmgr, bootmgr.efi, EFI\ and boot\,
# minus the BCD, which stays the PE's own) from any newer Windows 11 ISO, such as
# the 24H2/25H2 one from Microsoft, and rebuilds the ISO with UDF.
set -Eeuo pipefail
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO=$(cd -- "$HERE/.." && pwd)
# shellcheck source=scripts/common.sh
source "$REPO/scripts/common.sh"
trap on_err ERR

donor=${1:-}
pe=${2:-$REPO/pe/out/LazarusPE.iso}
[[ -f $donor ]] || die "pass a newer Windows 11 ISO: pe/fix-bootmgr.sh ~/Downloads/Win11_25H2_English_x64.iso"
[[ -f $pe ]] || die "no PE ISO at $pe"
need 7z 7zip
need mkisofs cdrtools
need xorriso libisoburn

work=$(mktemp -d "$(dirname "$pe")/.fix-bootmgr.XXXX")
trap 'rm -rf "$work"' EXIT

section "Newer boot manager from $(basename "$donor") into $(basename "$pe")"
7z x -y -o"$work/new" "$donor" bootmgr bootmgr.efi 'efi/*' 'boot/*' \
  -x'!boot/bcd' -x'!efi/microsoft/boot/bcd' -x'!boot/boot.sdi' >/dev/null
[[ -f $work/new/efi/boot/bootx64.efi && -f $work/new/efi/microsoft/boot/efisys_noprompt.bin ]] \
  || die "$(basename "$donor") doesn't look like a Windows ISO (no efi/boot/bootx64.efi)"
7z x -y -o"$work/iso" "$pe" >/dev/null   # 7-Zip reads the UDF names (xorriso would see 8.3 ones)
[[ -n $(find "$work/iso" -maxdepth 2 -ipath "*/sources/boot.wim" -type f) ]] || die "$(basename "$pe") has no sources/boot.wim"

top=$(find "$work/iso" -maxdepth 1 -iname bootmgr -type f | head -n1)   # keep the ISO's own spelling
cp -f "$work/new/bootmgr" "${top:-$work/iso/bootmgr}"
cp -f "$work/new/bootmgr.efi" "$work/iso/bootmgr.efi"
cp -rf "$work/new/efi/." "$work/iso/efi/"
cp -rf "$work/new/boot/." "$work/iso/boot/"
# The no-prompt image skips "Press any key to boot from CD", which a USB stick never needs
cp -f "$work/new/efi/microsoft/boot/efisys_noprompt.bin" "$work/iso/efi/microsoft/boot/efisys.bin"

label=$(xorriso -indev "$pe" 2>&1 | sed -n "s/^Volume id *: *'\(.*\)'/\1/p")
mkisofs -quiet -iso-level 3 -udf -J -joliet-long -l -D -N -relaxed-filenames -V "${label:-LAZARUSPE}" \
  -b boot/etfsboot.com -no-emul-boot -boot-load-size 8 -hide boot.catalog -hide-joliet boot.catalog \
  -eltorito-alt-boot -eltorito-platform efi -b efi/microsoft/boot/efisys.bin -no-emul-boot \
  -o "$work/out.iso" "$work/iso" 2>/dev/null
mv -f "$work/out.iso" "$pe"
ok "$(basename "$pe") now boots with the boot manager from $(basename "$donor")"
info "next: ./helix fetch lazarus-pe && ./refresh.sh"
