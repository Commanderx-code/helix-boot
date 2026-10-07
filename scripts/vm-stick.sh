#!/usr/bin/env bash
# Hand the Helix Boot stick to a virtual machine and take it back, so that it is never in both
# at once: two systems writing one stick corrupts it.
#   scripts/vm-stick.sh give win11     unmount it here, then attach it to the running VM
#   scripts/vm-stick.sh take win11     detach it from the VM and mount it here again
#                                      (eject it inside the VM first: "Safely remove", or Eject in the app.
#                                      That switches the stick off, so `take` then asks you to replug it.)
# The VM is a libvirt one on this PC: the system's (qemu:///system), or yours with
# LIBVIRT_DEFAULT_URI=qemu:///session. Only for as long as the VM runs: nothing is added to its settings.
set -Eeuo pipefail
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=scripts/common.sh
source "$HERE/scripts/common.sh"
trap on_err ERR

what=${1:-} vm=${2:-}
[[ $what == give || $what == take ]] && [[ -n $vm ]] || { sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }
[[ $vm =~ ^[A-Za-z0-9._-]+$ ]] || die "not a VM's name: $vm"
need virsh libvirt
conn=${LIBVIRT_DEFAULT_URI:-qemu:///system}
virsh_() { LC_ALL=C virsh -q -c "$conn" "$@"; }
[[ $(virsh_ domstate "$vm" 2>/dev/null) == running ]] || die "the VM '$vm' isn't running (start it first; the stick is handed to a running VM)"
note=${XDG_STATE_HOME:-$HOME/.local/state}/helix-boot/vm-stick-$vm.xml     # what was attached, to detach the same

if [[ $what == give ]]; then
  mapfile -t disks < <(lsblk -lnpo PKNAME,LABEL | awk '$2=="VTOYEFI"{print $1}' | sort -u)
  ((${#disks[@]})) || die "no Ventoy stick is plugged in here (is it in the VM already?)"
  ((${#disks[@]} == 1)) || die "more than one Ventoy stick is plugged in (${disks[*]}): unplug all but one"
  disk=${disks[0]}
  ids=$(udevadm info -q property -n "$disk" | awk -F= '$1=="ID_VENDOR_ID"{v=$2} $1=="ID_MODEL_ID"{m=$2} END{print v, m}')
  read -r vendor product <<< "$ids"
  [[ $vendor =~ ^[0-9a-fA-F]{4}$ && $product =~ ^[0-9a-fA-F]{4}$ ]] || die "$disk isn't a USB device this can hand over"
  sync
  while read -r part; do
    [[ -z $part ]] || unmount_part "$part" || die "$part is in use here: close what has it open, then try again"
  done < <(lsblk -lnpo NAME,TYPE "$disk" | awk '$2=="part"{print $1}')
  mkdir -p "$(dirname "$note")"
  printf "<hostdev mode='subsystem' type='usb' managed='yes'>\n  <source>\n    <vendor id='0x%s'/>\n    <product id='0x%s'/>\n  </source>\n</hostdev>\n" \
    "$vendor" "$product" > "$note"
  virsh_ attach-device "$vm" "$note" --live >/dev/null || { rm -f "$note"; die "couldn't attach the stick to '$vm'"; }
  ok "The stick is unmounted here and attached to '$vm'. Take it back with: scripts/vm-stick.sh take $vm"
else
  [[ -f $note ]] || die "this didn't give a stick to '$vm' (nothing noted in $note). Detach it in your VM manager."
  virsh_ detach-device "$vm" "$note" --live >/dev/null || die "couldn't detach the stick from '$vm' (is it still in use there?)"
  rm -f "$note"
  part='' told=0
  for _ in {1..150}; do       # it comes back to this system a moment later
    udevadm settle --timeout=5 2>/dev/null || true
    disk=$(lsblk -lnpo PKNAME,LABEL | awk '$2=="VTOYEFI"{print $1; exit}')
    if [[ -n $disk ]]; then part=$(first_partition "$disk"); fi
    [[ -n $part ]] && break
    # Ejected inside the VM, as it should be, a stick switches itself off ("safe to remove"): it is
    # back on this system as a disk with nothing in it, until it is unplugged and plugged in again.
    if ((!told)) && lsblk -dnbo SIZE,TRAN 2>/dev/null | awk '$2=="usb" && $1==0 {found=1} END{exit !found}'; then
      info "The stick was ejected inside the VM, so it has switched itself off. Unplug it and plug it in again …"
      told=1
    fi
    ((told)) || ((SECONDS < 25)) || break
    sleep 1
  done
  [[ -n $part ]] || die "the stick is detached from '$vm', but it hasn't shown up here: unplug it and plug it in again, then mount it as usual"
  mnt=$(mount_part "$part") || die "the stick is back as $part, but couldn't be mounted: ./check.sh, or Repair it"
  ok "The stick is back here, mounted at $mnt"
  dirty=$(journalctl -k --since '-1 min' --no-pager 2>/dev/null | grep -c "not properly unmounted" || true)
  [[ ${dirty:-0} == 0 ]] || warn "it wasn't ejected inside the VM before it was taken back: run a repair (sudo fsck -y $part) and ./check.sh"
fi
