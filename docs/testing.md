# Testing on real hardware

The tests in `tests/` and CI cover the engine, the apps' logic and booting in a
virtual PC. This page is for what only a real stick, a real Windows or a real
person can show. Each line says what to do and what should happen; the table
at the end records what has been tried.

## Windows app

Run `HelixBoot.exe` on a Windows PC, or in a Windows VM with the stick handed
to it (`scripts/vm-stick.sh give <vm>`).

1. **The window.** Every control is visible, the bottom row included, on a
   small screen too.
2. **Update stick**, tools from the internet. It shows what it will copy and
   asks. The bar shows gigabytes copied. It ends with "Done".
3. **Check stick.** It reads everything back and reports 0 damaged.
4. **Tools…** Untick a tool, Save, Update: it is removed. Tick it again,
   Update: it is back.
5. **Eject.** "… is ejected: safe to unplug", and the drive letter goes.
6. **Check for update**, on a version older than the latest release. It
   downloads, swaps itself, and offers to start the new version.
7. **Install Helix Boot** on a spare stick, with **Install tests the stick
   first** ticked. It asks for the disk number, tests, installs Ventoy and
   fills the stick.
8. **Repair stick** on a stick that an update says is damaged.
9. On a PC whose antivirus blocks a tool: the install finishes, and the end
   names the tool that was left out.

## Linux window

`./HelixBoot-linux-x86_64`, or `python3 linux/helix_gui.py` from a clone.

1. **Update stick** and **Check stick**, as above.
2. **Install Helix Boot** on a spare stick. The desktop's password dialog
   appears once, for Ventoy. The stick is filled and mounted.
3. **Eject.** The stick is unmounted and switched off.
4. **Repair stick.** The password dialog appears, `fsck` runs, the stick is
   mounted again.
5. `--add-launcher`: Helix Boot is in the applications menu and starts from it.

## Mac

On a Mac, with the stick plugged in: `./HelixBoot-mac-arm64` (or `-x86_64`).

1. `list` shows the stick. `update` asks, then updates it. `check` passes.
2. One Mac tool from the stick's `Mac` folder opens.
3. `self-update`, on a version older than the latest release.

## Booting the stick on a real PC

1. The splash shows for a second, then the menu, with icons.
2. **L** opens the power menu (reboot, power off). **F1** starts Memtest86+.
3. One image from each category boots.
4. Lazarus PE: the taskbar shows, and the launcher lists the apps.
5. On a Secure Boot PC: the first boot asks to enrol Ventoy's key.

## Sharing a pack

1. `helix pack --public --split`, then on a Windows PC: double-click
   `build-stick.cmd` in the pieces folder. It joins, checks and starts the app,
   and the app finds the pack.

## What has been tried

| What | Where | Result |
|---|---|---|
| Windows app: the window, all controls, five buttons in the bottom row | Windows 11 VM, 0.7.5 | Works. On a 1280 x 800 screen Windows placed it with the bottom row under the taskbar: it is centred from the next release |
| Windows app: Tools… | Windows 11 VM, 0.7.5 | Opens, lists every tool by category |
| Windows app: Eject | Windows 11 VM, 0.7.5, real stick | Works: "F: is ejected: safe to unplug" |
| Windows app: self-update | Windows 11 VM, 0.7.4 to 0.7.5 | Works: downloaded, verified, swapped, the old program kept aside |
| Windows app: a tool blocked by antivirus | A friend's PC, 0.7.3 | Works: the tool is left out and named |
| Windows app: Update stick | Windows 11 VM, 0.6.9 | Worked then; not repeated since |
| `build-stick.cmd` made by `helix pack --split` | Windows 11 VM | Works: joined 3 pieces, checked, took the app out, started it |
| `scripts/vm-stick.sh give` / `take` | This PC, real stick | `give` works. After Eject in Windows the stick is switched off, so `take` needs it replugged: it now says so and waits |
| Linux window: Update stick | This PC, real stick, 0.7.3 | Works |
| Linux window: Install, Eject, Repair, the launcher | | Not tried |
| Windows app: Install with the stick test, Repair stick, Update on 0.7.5 | | Not tried |
| "Start the new version now?" after an update in the window | | Not tried (the swap itself was, from the command line) |
| Mac program on a real Mac | | Not tried (CI runs it on GitHub's Macs, against disk images) |
| Booting the stick on a real PC: L, F1, Lazarus's taskbar, Secure Boot | | Not tried (CI boots it in a virtual PC) |
| A public, split pack opened on someone else's PC | | Not tried |
