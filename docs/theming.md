# HELIXBOOT themes

The default Ventoy theme is **Helix Neon**: near-black, violet and cyan, with
DNA branding and the tagline **RECOVERY • DIAGNOSTICS • REPAIR**. Six presets
sit beside it: Midnight, Ember, Terminal and Slate, the same menu in other
colours, and Standby and Poly dark, two other people's GRUB themes adapted for
Ventoy. The separate Lazarus PE PortableApps theme remains green and keeps the
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
Ventoy's tips and version, and the loading bar's two colours). Add one to
`PRESETS` in `theme/build-theme.py` and re-run it.

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

- `docs/artwork/helix-purple-source.png`: text-free source artwork.
- `theme/build-theme.py`: wordmark, small DNA logo, palette, icons and boxes.
- `docs/artwork/helix-icons/`: the icon masters, one per menu class, and the
  rest of the collection in `more/`; see [icon notes](tool-icons.md).
- `theme/theme.txt`: live menu layout, fonts, timeout and Ventoy status labels.
- `theme/presets/`, `theme/icon-packs/`: the presets and the letter-badge icon
  pack, generated by the same run (see "Change a stick's look").
- `helix`: matching menu-tip position/colour and Ventoy version placement.
- `docs/artwork/helix-neon-preview.jpg`: offline preview of the committed assets.

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

`docs/artwork/helix-purple-source.png` is a text-free version of the purple
HELIXBOOT mockup: the purple/electric-blue DNA helix, planet, nebula, mountains
and reflective water on the right, with no text, logo, panel, icon, selection
or hotkey, the left side kept dark and calm for the live menu and the bottom
dark for status. `build-theme.py` adds the wordmark and tagline, so they are
exact and reproducible.

Layout properties follow the [GNU GRUB theme format](https://www.gnu.org/software/grub/manual/grub/html_node/Theme-file-format.html).
