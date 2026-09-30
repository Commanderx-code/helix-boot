# HELIXBOOT themes

The Ventoy theme is **Helix Neon**: near-black, violet and cyan, with DNA
branding and the tagline **RECOVERY • DIAGNOSTICS • REPAIR**. The separate
Lazarus PE PortableApps theme remains green and keeps the Retro Dark slot.
The other five PortableApps themes and the user's saved selection are unchanged.

## Apply

Run `./refresh.sh` with the stick attached. The normal refresh copies the committed theme assets and writes
Ventoy's menu configuration. It also checks for tool updates as usual.
No Windows PE rebuild or PortableApps reinstall is needed.

To keep Ventoy's stock appearance, set `theme = ""` in `[settings]` in
`local.toml`, then refresh. Custom icons in `byo/icons/` still take priority.

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
- `docs/artwork/tool-icons/`: curated icon masters and their source registry;
  see [tool icon notes](tool-icons.md). Rebuilds preserve their original colours.
- `theme/theme.txt`: live menu layout, fonts, timeout and Ventoy status labels.
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
