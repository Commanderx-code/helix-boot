# Roadmap

**Next**

| Planned | |
|---|---|
| A code-signed `HelixBoot.exe` | So Windows shows a verified publisher. The [signing policy](code-signing.md) is in place; the application to SignPath Foundation is next. |
| A category for legacy PCs | 32-bit and BIOS-only tools, for machines too old for the rest of the stick. |
| Icon sets per theme | The same icons redrawn in each theme's colours. |

**Shipped**

| Area | What's there | Since |
|---|---|---|
| The stick | Manifest of tools, verified downloads, installer and refresher, Ventoy menu | 0.1 |
| | Packs: the whole stick in one offline, self-installing zip | 0.3 |
| | Updates that keep another PC's tools; a renamed stick is still recognised | 0.6.2 |
| | Checking a stick for damage; Helix Boot on the stick itself | 0.6.4 – 0.6.6 |
| Boot menu | Helix Neon theme | 0.5 |
| | A splash with a loading bar | 0.6.0 |
| | Theme builder: seven themes, icon styles, your own background and splash, saved looks | 0.6.0 – 0.6.6 |
| | One icon set from the HELIXBOOT collection | 0.6.7 |
| | Hotkeys as a row of icons; a power menu on L, Memtest86+ on F1 | 0.6.8 |
| Windows app | `HelixBoot.exe`: install, update, packs, an update summary first | 0.1 – 0.6.4 |
| | The Look window, Check stick, newer-version notices | 0.6.0 – 0.6.6 |
| | A dark, compact look and the HB logo; adds the splash and menu keys like Linux | 0.6.8 – 0.6.9 |
| Linux | One-file installer (`HelixBoot.sh`) | 0.5.2 |
| | The window, as on Windows: `HelixBoot-linux-x86_64` | 0.7.4 |
| Lazarus PE | PhoenixPE preset and build VM, the Lazarus launcher, PortableApps.com with Helix themes | 0.1 – 0.5.1 |
| Mac | 32 tools for a working Mac, each opened and checked on a real Mac in CI | 0.6.1 – 0.6.12 |
| | Updating a stick from a Mac; creating one (experimental) | 0.6.14 |
| | One-file download for Apple Silicon Macs | 0.7.0 |
| | One-file download for Intel Macs | 0.7.2 |
| Stick health | A repair command for a damaged filesystem; a memory of damage | 0.7.1 |
| | Testing a stick before installing; check reminders; Repair stick in the Windows app | 0.7.2 |
| Trust | CI: tests, a boot test of every theme, a weekly live download and verify of every tool | 0.1 – 0.6.4 |
| | Checksums and build attestations on every release | 0.6.6 |
| | Hardening: the confirmed disk is the one written, plain file trees only, pinned download sites | 0.6.11 – 0.6.13 |

The [changelog](../CHANGELOG.md) has every release in detail. [Testing on real hardware](testing.md) says what has been tried on a real stick, Windows and Mac, and what hasn't.
