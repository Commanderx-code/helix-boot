#!/usr/bin/env bash
# Helix Boot — a Windows 11 VM for building Lazarus PE.
#
#   pe/vm/build-vm.sh create ~/Downloads/Win11.iso   make the VM, start Windows setup
#   pe/vm/build-vm.sh push                           copy pe/ tooling onto the transfer disk
#   pe/vm/build-vm.sh start                          boot the VM and open its window
#   pe/vm/build-vm.sh pull                           copy the built ISO to pe/out/LazarusPE.iso
#
# No root needed: the VM runs in your user's libvirt session (qemu:///session),
# and files move through a small FAT32 "transfer" disk that this script reads
# and writes with mtools while the VM is off.
set -Eeuo pipefail
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO=$(cd -- "$HERE/../.." && pwd)
# shellcheck source=scripts/common.sh
source "$REPO/scripts/common.sh"
trap on_err ERR

CONN=${CRVM_CONNECT:-qemu:///session}
DATA=${XDG_DATA_HOME:-$HOME/.local/share}
# A VM made before the rename to Helix Boot keeps its folder and name: libvirt records its disks' paths.
if [[ -z ${CRVM_DIR:-} && ! -d $DATA/helix-boot/vm && -d $DATA/commander-rescue/vm ]]; then
  DIR=$DATA/commander-rescue/vm
else
  DIR=${CRVM_DIR:-$DATA/helix-boot/vm}
fi
if [[ -n ${CRVM_NAME:-} ]]; then
  VM=$CRVM_NAME
elif [[ $DIR == */commander-rescue/vm ]]; then
  VM=commander-pe-build                 # made before the rename; see DIR above
else
  VM=helix-pe-build
fi
DISK=$DIR/windows.qcow2
XFER=$DIR/transfer.img
XFER_GB=16
PART_OFFSET=1048576          # transfer partition starts at 1 MiB
export MTOOLS_SKIP_CHECK=1
M="$XFER@@$PART_OFFSET"      # mtools image@@offset syntax

usage() {
  cat <<EOF
Usage: pe/vm/build-vm.sh <command>

  create <windows.iso>  create the VM (Windows 11, UEFI + TPM, ${XFER_GB} GB transfer disk)
                        and start Windows setup from the ISO
  start                 boot the VM and open its window
  push                  refresh the transfer disk with this repo's pe/ folder (VM must be off)
  pull                  copy the newest ISO from the transfer disk's out folder to
                        pe/out/LazarusPE.iso (VM must be off)
  status                show the VM's state and what's on the transfer disk
  destroy               delete the VM and its disks

Files live in $DIR
EOF
}

virsh_() { virsh -q -c "$CONN" "$@"; }
exists() { virsh_ dominfo "$VM" >/dev/null 2>&1; }
running() { [[ $(virsh_ domstate "$VM" 2>/dev/null) == running ]]; }
need_off() {
  running && die "the VM is running. Shut Windows down first (Start → Power → Shut down)."
  return 0
}
need_xfer() { [[ -f $XFER ]] || die "no transfer disk yet — run: pe/vm/build-vm.sh create <windows.iso>"; }

open_window() {
  if command -v virt-viewer >/dev/null; then
    (virt-viewer -c "$CONN" --wait "$VM" >/dev/null 2>&1 &)
  else
    info "open it with: virt-manager, File → Add Connection → QEMU/KVM user session"
  fi
}

make_transfer() {
  info "creating ${XFER_GB} GB transfer disk"
  truncate -s "${XFER_GB}G" "$XFER"
  printf 'label: dos\nstart=%d, type=c\n' $((PART_OFFSET / 512)) | sfdisk -q "$XFER"
  local blocks=$(( (XFER_GB * 1024 ** 3 - PART_OFFSET) / 1024 ))
  mkfs.vfat -F 32 -n CRTRANSFER --offset $((PART_OFFSET / 512)) "$XFER" "$blocks" >/dev/null
  mmd -i "$M" ::/out
}

push() {
  need_xfer
  need_off
  mdeltree -i "$M" ::/commander 2>/dev/null || true   # its name before the rename to Helix Boot
  mdeltree -i "$M" ::/helix 2>/dev/null || true
  mmd -i "$M" ::/helix
  mcopy -i "$M" -s -m "$REPO/pe/phoenixpe" "$REPO/pe/launcher" "$REPO/pe/README.md" ::/helix/
  # A PhoenixPE release saved in $DIR rides along, so Windows needn't download it
  local pe_zip='' step1='1. Unpack PhoenixPE (https://github.com/PhoenixPE/PhoenixPE/releases) to C:\PhoenixPE'
  pe_zip=$(find "$DIR" -maxdepth 1 -name 'PhoenixPE-*.7z' -printf '%f\n' | sort -V | tail -n1)
  if [[ -n $pe_zip ]]; then
    mdel -i "$M" '::/PhoenixPE-*.7z' 2>/dev/null || true
    mcopy -i "$M" -o -m "$DIR/$pe_zip" ::/
    step1="1. Right-click $pe_zip on this disk, Extract All, and extract to C:\PhoenixPE"
  fi
  # Unpacked drivers in $DIR/drivers/x64 (e.g. Intel Wi-Fi) ride along for Driver Integration
  local drivers='' step3b='   (Extra drivers: put unpacked .inf folders in C:\PhoenixPE\Workbench\Drivers\x64)'
  mdeltree -i "$M" ::/drivers 2>/dev/null || true
  if [[ -d $DIR/drivers/x64 ]] && [[ -n $(ls -A "$DIR/drivers/x64") ]]; then
    mcopy -i "$M" -s -m "$DIR/drivers" ::/
    drivers=$(find "$DIR/drivers/x64" -mindepth 1 -maxdepth 1 -printf '%f ' | sed 's/ $//')
    step3b='   Drivers > Driver Integration: tick it and set "x64 Drivers" to D:\drivers\x64'
  fi
  # Anything else for the build (a wallpaper image, ...) rides along from $DIR/extra
  mdeltree -i "$M" ::/extra 2>/dev/null || true
  local extra=''
  if [[ -d $DIR/extra ]] && [[ -n $(ls -A "$DIR/extra") ]]; then
    mcopy -i "$M" -s -m "$DIR/extra" ::/
    extra=$(find "$DIR/extra" -mindepth 1 -maxdepth 1 -printf '%f ' | sed 's/ $//')
  fi
  printf '%s\r\n' \
    'Helix Boot transfer disk' \
    '' \
    'Before anything else: Windows Security > Virus & threat protection > Manage settings >' \
    'Tamper Protection off, then in Terminal (Admin):' \
    "     Add-MpPreference -ExclusionPath 'C:\\PhoenixPE','D:\\'" \
    '  (D: is this disk.) Defender flags some PhoenixPE tools; exclusions stop it for good.' \
    '' \
    "$step1" \
    '2. In PowerShell, from helix\phoenixpe on this disk:' \
    '     powershell -ExecutionPolicy Bypass -File .\Apply-HelixPreset.ps1 C:\PhoenixPE' \
    '3. Run C:\PhoenixPE\PEBakeryLauncher.exe as administrator. Source Config: the Windows DVD' \
    '   drive root, base image 2, the Pro edition, "Run all programs from RAM" NOT ticked.' \
    "$step3b" \
    '   Then Build.' \
    '   (Files for the build, e.g. a wallpaper image for Tweaks > Wallpaper > Use Custom' \
    '    Wallpaper, are in D:\extra.)' \
    '4. Copy the finished .iso into the out folder on this disk, then shut Windows down.' \
    '5. On Linux: pe/vm/build-vm.sh pull' > "$DIR/README.txt"
  mcopy -i "$M" -o "$DIR/README.txt" ::/README.txt
  ok "transfer disk updated (helix\\, README.txt${pe_zip:+, $pe_zip}${drivers:+, drivers: $drivers}${extra:+, extra: $extra})"
}

case ${1:-} in
  create)
    iso=${2:-}
    [[ -f $iso ]] || die "pass your Windows 11 ISO: pe/vm/build-vm.sh create ~/Downloads/Win11_25H2_English_x64.iso"
    need virsh libvirt
    need virt-install
    need qemu-img qemu-desktop
    need swtpm
    need sfdisk util-linux
    need mkfs.vfat dosfstools
    need mcopy mtools
    [[ -e /dev/kvm ]] || die "/dev/kvm is missing — enable virtualization (VT-x/AMD-V) in your BIOS"
    exists && die "VM '$VM' already exists. Use 'start', or 'destroy' to begin again."
    # The session libvirt raises QEMU's core-dump limit to unlimited unless told otherwise,
    # which fails where the hard limit is 0 (Garuda's default). Pin it to 0 instead.
    qconf=${XDG_CONFIG_HOME:-$HOME/.config}/libvirt/qemu.conf
    if [[ $(ulimit -Hc) == 0 ]] && ! grep -qs '^[[:space:]]*max_core' "$qconf"; then
      mkdir -p "$(dirname "$qconf")"
      printf '# Added by Helix Boot: core dumps are disabled for this user\nmax_core = 0\n' >> "$qconf"
      pkill -u "$(id -u)" -x virtqemud || true  # restarts on demand with the new setting
      info "set max_core = 0 in $qconf (core dumps are off for your user)"
    fi
    mkdir -p "$DIR"
    [[ -f $XFER ]] || make_transfer
    push
    iso=$(realpath "$iso")
    section "Creating VM '$VM'"
    virt-install -q --connect "$CONN" --name "$VM" --osinfo win11 \
      --memory 6144 --vcpus 4 --cpu host-passthrough \
      --boot uefi --tpm backend.type=emulator,backend.version=2.0,model=tpm-crb \
      --disk "path=$DISK,size=64,format=qcow2,bus=sata" \
      --disk "path=$XFER,format=raw,bus=sata" \
      --cdrom "$iso" \
      --network user,model=e1000e \
      --graphics spice --noautoconsole
    open_window
    ok "Windows setup is starting in the VM window."
    info "If it says 'Press any key to boot from CD', click in the window and press a key."
    info "No product key needed: choose 'I don't have a product key', edition Windows 11 Pro."
    info "Setup's first restart powers the VM off (virt-install does that once). Run 'start' to carry on."
    info "Then follow the transfer disk's README.txt (it shows up as a drive in Explorer)."
    ;;
  start)
    exists || die "no VM yet — run: pe/vm/build-vm.sh create <windows.iso>"
    running || virsh_ start "$VM" >/dev/null
    open_window
    ok "VM '$VM' is running"
    ;;
  push) push ;;
  pull)
    need_xfer
    need_off
    tmp=$(mktemp -d)
    mcopy -i "$M" -n -m '::/out/*.iso' "$tmp/" 2>/dev/null || true
    newest=$(find "$tmp" -maxdepth 1 -iname '*.iso' -printf '%T@\t%p\n' | sort -rn | head -n1 | cut -f2)
    if [[ -z $newest ]]; then rm -rf "$tmp"; die "no .iso in the transfer disk's out folder — copy the build there first"; fi
    mkdir -p "$REPO/pe/out"
    mv -f "$newest" "$REPO/pe/out/LazarusPE.iso"
    rm -rf "$tmp"
    ok "pe/out/LazarusPE.iso ← $(basename "$newest") ($(du -h "$REPO/pe/out/LazarusPE.iso" | cut -f1))"
    info "next: ./helix fetch lazarus-pe && ./refresh.sh"
    ;;
  status)
    if exists; then info "VM '$VM': $(virsh_ domstate "$VM")"; else info "VM '$VM': not created"; fi
    if [[ -f $XFER ]]; then
      if running; then
        info "transfer disk: in use by the VM"
      else
        mdir -i "$M" ::/out 2>/dev/null | grep -i ' iso ' || info "transfer disk: no ISO in out\\ yet"
      fi
    fi
    ;;
  destroy)
    exists || [[ -d $DIR ]] || die "nothing to delete"
    read -rp "Delete VM '$VM' and everything in $DIR? Type yes: " a
    [[ $a == yes ]] || die "kept everything"
    if exists; then
      running && virsh_ destroy "$VM" >/dev/null
      virsh_ undefine "$VM" --nvram --tpm >/dev/null 2>&1 || virsh_ undefine "$VM" --nvram >/dev/null
    fi
    rm -rf "$DIR"
    ok "deleted"
    ;;
  -h|--help|'') usage ;;
  *) usage; die "unknown command: $1" ;;
esac
