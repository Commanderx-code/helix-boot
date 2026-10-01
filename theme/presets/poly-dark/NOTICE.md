# Poly dark

A GRUB theme by Andrei Shevchuk, from <https://github.com/shvchk/poly-dark>
(<https://store.kde.org/p/1230780>), under the MIT licence in `LICENSE`.

Changed for Helix Boot / Ventoy:

- `theme.txt`: the list is in DejaVu Sans Mono at 20 px (the theme's 16 px
  Unifont is hard to read at 1920×1080), the rest in Ventoy's built-in Unifont
  instead of the theme's own copy; icon sizes named; Ventoy's hotkey line and boot-mode indicators replace the
  navigation hint; the other languages' countdown texts are left out.
- Its operating-system icons are left out: the menu shows Helix Boot's tool
  icons, in greyscale.
- `splash.png` and `preset.toml` are made by `theme/build-theme.py`.
