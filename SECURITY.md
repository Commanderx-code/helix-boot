# Security policy

Commander Rescue downloads bootable images and writes them to disks, so
integrity problems matter. Examples worth reporting:

- a way to make `crescue` accept a download that fails verification;
- path traversal or other unsafe writes when fetching, syncing or unpacking a pack;
- `install.sh` or the Windows app selecting a disk it should refuse;
- an upstream tool that has been tampered with, or a checksum source that is wrong.

## Reporting

Please report privately through
[GitHub security advisories](https://github.com/Commanderx-code/commander-rescue/security/advisories/new)
rather than in a public issue. Include the steps to reproduce and the version
(`./crescue --version`). You'll get a reply as soon as possible, and a fix will
be released before the details are made public.

Only the latest release and `main` receive security fixes.
