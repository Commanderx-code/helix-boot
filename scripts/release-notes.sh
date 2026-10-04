#!/usr/bin/env bash
# Print one version's section of CHANGELOG.md, for its release page.
#   scripts/release-notes.sh v0.6.13      (the leading v is optional)
set -Eeuo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
version=${1:?usage: release-notes.sh VERSION}
version=${version#v}
[[ $version =~ ^[0-9]+(\.[0-9]+){1,2}$ ]] || { echo "not a version: $1" >&2; exit 1; }
notes=$(awk -v want="## [$version]" '
  index($0, want) == 1 { on = 1; next }
  on && /^## \[/       { exit }
  on && /^\[[^]]+\]: / { exit }          # the link list at the end of the file
  on' "$here/../CHANGELOG.md")
# Without the blank lines around it; nothing found is an error, so a release never goes out empty.
notes=$(printf '%s\n' "$notes" | sed -e '/./,$!d' | sed -e ':a' -e '/^\n*$/{$d;N;ba' -e '}')
[[ -n $notes ]] || { echo "CHANGELOG.md has no section for $version" >&2; exit 1; }
# A release page shows every line break, so each wrapped paragraph and bullet becomes one line
# (headings, new bullets, table rows and code blocks start their own).
printf '%s\n' "$notes" | awk '
  /^```/                        { flush(); print; code = !code; next }
  code                          { print; next }
  /^[[:space:]]*$/              { flush(); print ""; next }
  /^(#|\|)/                     { flush(); print; next }
  /^[[:space:]]*([-*]|[0-9]+\.) / { flush(); line = $0; next }
                                { sub(/^[[:space:]]+/, ""); line = (line == "" ? $0 : line " " $0) }
  function flush() { if (line != "") { print line; line = "" } }
  END { flush() }' |
  # … and a link to a file in the repo has to say where the repo is, at this version
  sed -E "s#\\]\\((docs|scripts|theme|pe|mac|tests|windows|linux|byo)/#](https://github.com/${GITHUB_REPOSITORY:-Commanderx-code/helix-boot}/blob/v$version/\\1/#g"
