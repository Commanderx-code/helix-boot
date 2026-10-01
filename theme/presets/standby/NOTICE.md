# Standby

A GRUB theme by Llewelyn Trahaearn, with resources by vinceliuice
([grub2-themes](https://github.com/vinceliuice/grub2-themes), GPL-3.0), from
<https://store.kde.org/p/1172610> (version 1.7). Distributed under the GNU
General Public Licence; a copy is in `COPYING`. It is not covered by Helix
Boot's MIT licence.

Changed for Helix Boot / Ventoy:

- `theme.txt`: no title text; the power symbol is always shown (the original
  shows it only while a timeout counts down); Ventoy's hotkey line and
  boot-mode indicators replace GRUB's key help; the background is stretched to
  the screen.
- Its operating-system icons are left out: the menu shows Helix Boot's tool
  icons, in greyscale.
- `splash.png` and `preset.toml` are made by `theme/build-theme.py`.

The fonts are NanumMyeongjo and Source Code Pro (both SIL Open Font License),
as GRUB fonts, unchanged from the theme.
