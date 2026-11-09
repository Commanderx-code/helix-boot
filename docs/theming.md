# HELIXBOOT themes

The default Ventoy theme is **Helix Steel**: brushed metal, violet and cyan,
with DNA branding and the tagline **RECOVERY • DIAGNOSTICS • REPAIR**. Seven
presets sit beside it: Moon, Horizon, Nebula, Circuit and Scope, the same menu
over other artwork, and Standby and Poly dark, two other people's GRUB themes
adapted for Ventoy. The separate Lazarus PE PortableApps theme remains green and keeps the
Retro Dark slot. The other five PortableApps themes and the user's saved
selection are unchanged.

## Apply

Run `./refresh.sh` with the stick attached. The normal refresh copies the
committed theme assets, presets included, and writes Ventoy's menu
configuration. It also checks for tool updates as usual. No Windows PE rebuild
or PortableApps reinstall is needed. The stick keeps the look it had.

To keep Ventoy's stock appearance, set `theme = ""` in `[settings]` in
`local.toml`, then refresh.

## Change a stick's look

`./theme.sh` (or `helix theme <mount point>`) switches a finished stick between
the presets, icon packs, your own background and splash. The plain choice is
Standby (`--theme off` gives it too), not Ventoy's own white look;
`./theme.sh --help` lists the options, `./theme.sh --menu` asks instead, and the
Windows app has a **Look…** window with the same choices. It works on the stick
alone, so it needs no downloads and no rebuild. The preview (`--preview FILE`,
`p` in the menu, the picture in the Look window) is drawn with Pillow from the
same files the stick would get; it is a close sketch, not a boot capture.

| On the stick | What it is |
|---|---|
| `.helix-boot/theme/` | The theme as refresh wrote it: the default, `presets/<id>/`, `icon-packs/<id>/`, and your own icons and splash from `byo/` in `mine/` |
| `.helix-boot/ventoy.base.json` | The boot menu before the look is applied |
| `.helix-boot/look.json` | The choice: `theme`, `icons`, `background`, `splash` |
| `.helix-boot/look/` | Your own `background.png` and `splash.png`, set with `--background` / `--splash` |
| `ventoy/theme/`, `ventoy/ventoy.json` | What Ventoy reads: built from the four above |

Refresh rewrites the first two and rebuilds the last, so the look survives it.
Don't edit `ventoy/theme/` by hand: it is rebuilt each time.

`--export ZIP` saves the look to a small zip: `look.json`, your pictures from
`look/`, and your icons and splash from `mine/`. **Save look…** in the Look
window does the same. `--import ZIP` (or **Load look…**) puts it back, on the
same stick or another, after checking that the zip holds only those pictures.
A theme or icon pack that the stick doesn't have falls back to the default.
The loaded icons and splash are marked as the stick's own, so an update keeps
them unless the updating PC has its own in `byo/`.

Icons are layered, later ones winning: the theme's, the preset's if it brings
any, yours from `byo/icons/`, then the icon pack you picked. The splash is yours (`--splash PICTURE`, else
`byo/splash.png`) or else the theme's; `--splash theme` uses the theme's even
when you have your own.

Icons can also be redrawn: `--icons grey` shows them all in shades of grey (a
flat one-colour icon turns white), `--icons logos` keeps them in colour, and
the default, `auto`, leaves it to the theme (Standby and Poly dark ask for
grey). That needs Pillow; without it they stay in colour.

A preset is a folder, `theme/presets/<id>/`, holding what differs from the
theme: `theme.txt`, the background and splash, the box images, any icons of
its own (`icons/`), and `preset.toml` (title, description, the `muted` text colour for
Ventoy's tips and version, and the loading bar's two colours). To add one, put
its 16:9 picture in `docs/artwork/themes/<id>.png`, add it to `PRESETS` in
`theme/build-theme.py` (with where its footer rule leaves room for the hotkey
row and Ventoy's version text) and re-run it.

Someone else's GRUB theme can be a preset too, as Standby and Poly dark are:
copy its files into `theme/presets/<id>/` with its licence and a `NOTICE.md`,
and say `standalone = true` in `preset.toml`, so the Helix theme's boxes and
fonts aren't laid under it. Its `theme.txt` needs `title-text: ""`, an
`icon_width` / `icon_height` / `item_icon_space` in `boot_menu`, and Ventoy's
`@VTOY_HOTKEY_TIP@` and boot-mode labels (copy those blocks from a preset
here). `preset.toml` can also set `icons = "grey"`, and where Ventoy's tip line
and version text go in that layout: `tip = ["33%", "77%"]`,
`version = ["84%", "96%"]`. `plain = true` makes it the plain choice: `off` is
then no longer offered, and means this preset. List it in `IMPORTED` in `theme/build-theme.py`
for a splash in its colours. An icon pack is a folder of
PNGs named after the tools (`theme/icon-packs/<id>/`, or your own in
`byo/icon-packs/<id>/`), with an optional `pack.toml` (`title`, `description`).

## Build

On Arch/Garuda:

```sh
sudo pacman -S --needed python-pillow grub ttf-dejavu
python3 theme/build-theme.py
python3 theme/preview-theme.py
```

If the fonts have not changed, `python3 theme/build-theme.py --skip-fonts`
uses the committed GRUB fonts and needs only Pillow and the DejaVu TTFs.
`--local` still only generates missing badges for tools in `local.toml`.

- `docs/artwork/themes/`: the backgrounds, wordmark and footer included:
  `steel.png` for the default theme and one per preset.
- `theme/build-theme.py`: palette, icons and boxes, and the presets'
  backgrounds, `theme.txt` and `preset.toml`.
- `docs/artwork/helix-icons/`: the icon masters, one per menu class, and the
  rest of the collection in `more/`; see [icon notes](tool-icons.md).
- `theme/theme.txt`: live menu layout, fonts, timeout and Ventoy status labels.
  The hotkey row at the bottom is an icon per key (`key_*.png`, made by
  `build-theme.py`) with the key above it, placed in pixels. It stands in for
  Ventoy's own `@VTOY_HOTKEY_TIP@` line of words: L Language, F1 Help,
  F2 Browse, F3 Tree view, F4 Local boot, F5 Tools, F6 Menu.

  L and F1 can do more on a rescue stick: **L a power menu, F1 Memtest86+**.
  A theme can't change what a key does, so `helix splash` adds a hook to
  Ventoy's boot script (with the splash) that runs `ventoy/helix-keys.cfg`
  from the stick, and notes on the stick that it did (`.helix-boot/keys-hook`).
  The Windows app does the same on Install and Update: Ventoy's partition has
  no drive letter there, so it reaches the script by the volume's id.
  With that note, the look is built with `key_power.png` and `key_mem.png` in
  place of `key_lang.png` and `key_help.png`, and the two scripts are written
  (`helix-keys.cfg`, `helix-power.cfg`). Without it, or on a theme with
  Ventoy's own line, the keys are Ventoy's and the scripts aren't there. So
  the row always shows what the keys do. Memtest86+ starts through Ventoy's
  own load-into-memory functions; if it isn't on the stick, F1 says so.
- `theme/presets/`, `theme/icon-packs/`: the presets and the letter-badge icon
  pack, generated by the same run (see "Change a stick's look").
- `helix`: matching menu-tip position/colour and Ventoy version placement.
- `docs/artwork/helix-preview.jpg`: offline preview of the committed assets.

The source and preview stay under `docs/`, so refresh does not copy them to
the stick. The generated background contains branding, but no baked-in menu,
search box, selected row, app icons or hotkey buttons. Ventoy supplies the
actual entries, status, timeout and hotkey text.

## Check on hardware

The primary layout is 1920×1080. Ventoy's existing `resolution_fit` fallback
remains enabled. At smaller resolutions fewer rows fit, so the menu scrolls.
Ventoy's left/right keys slide the highlighted name sideways; that's built into
Ventoy and can't be switched off. The background stretches to the available
screen, including 4:3 displays.

Offline previews can catch basic fit problems:

```sh
python3 theme/preview-theme.py --size 1280x720 --out /tmp/helix-720p.png
python3 theme/preview-theme.py --size 1024x768 --out /tmp/helix-4x3.png
```

These previews approximate GRUB layout; they do not execute Ventoy. The
screenshots in the README (`docs/boot-menu*.jpg`) are real Ventoy 1.1.17
renders, taken by booting a stick's `ventoy/` folder in a UEFI virtual machine. After
refreshing, boot the stick and check all category rows, entering a category,
long names, scrolling, F1/F2/F3, Enter/Esc, timeout (if configured), and any
boot-mode indicators you use. Check UEFI and legacy BIOS when available.

## Artwork provenance

`docs/artwork/themes/` holds the theme backgrounds: a cyan and violet DNA
helix on the right, the HELIXBOOT wordmark and tagline at the top left, and a
footer rule with HELIX TECH © and MULTIBOOT RECOVERY ENVIRONMENT. They have no
menu, panel, icon, selection or hotkey; the left side is kept dark for the live
menu. Each picture's footer rule sits at its own height, so the theme and each
preset place the hotkey row and Ventoy's version text above it (`HOTKEYS`,
`VERSION` and `PRESETS` in `build-theme.py`).

`docs/artwork/helix-logo.png` is the project's logo, the HB mark with a USB
stick and a DNA zipper on a clear background, at the top of the README.
`docs/artwork/helix-banner.png` is the same mark beside the HELIX BOOT name and
the RECOVERY • DIAGNOSTICS • REPAIR tagline: the app windows' header
(`windows/logo.png`, 84 px high, is made from it).
`docs/artwork/helix-app-icon.png` is the app icon, a USB stick with a cyan and
violet helix: the windows' own icon and the Windows program's file icon
(`windows/icon.png` and `windows/HelixBoot.ico` are made from it). All three
were supplied by the project's maintainer.

`docs/artwork/helix-splash.png` is the default theme's splash: the HB logo and
HELIXBOOT wordmark over a night landscape, supplied by the project's
maintainer and used as it is. The presets' splashes are still drawn by
`build-theme.py`, each in its own colours.

Layout properties follow the [GNU GRUB theme format](https://www.gnu.org/software/grub/manual/grub/html_node/Theme-file-format.html).
