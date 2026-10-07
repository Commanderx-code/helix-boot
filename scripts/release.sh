#!/usr/bin/env bash
# Cut a release, in the one order that works: version, changelog, tag, the build on GitHub,
# and only then the pack, so the pack carries this release's HelixBoot.exe and not the last.
#   scripts/release.sh 0.7.1 "what is new, in a few words"
#   scripts/release.sh 0.7.1 "…" --no-pack     no pack afterwards
#   scripts/release.sh 0.7.1 "…" --yes         don't ask before pushing
#   scripts/release.sh --pack                  only the last step: fetch, and a pack of this version
# What is released is CHANGELOG.md's [Unreleased] section. A pack holds your own tools: keep it private.
set -Eeuo pipefail
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=scripts/common.sh
source "$HERE/scripts/common.sh"
trap on_err ERR
cd "$HERE"

pack() {
  section "Pack"
  # A site that is down keeps the copy already fetched and verified; a pack without this release's app is refused
  ./helix fetch --outage-ok
  ./helix pack --need-app
}

version='' title='' do_pack=1 yes=0
while (($#)); do
  case $1 in
    --pack)    pack; exit ;;
    --no-pack) do_pack=0 ;;
    --yes|-y)  yes=1 ;;
    -h|--help) sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'; exit ;;
    -*)        die "unknown option $1" ;;
    *)         if [[ -z $version ]]; then version=${1#v}; elif [[ -z $title ]]; then title=$1; else die "unexpected: $1"; fi ;;
  esac
  shift
done
[[ $version =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "usage: scripts/release.sh VERSION \"what is new\"   (VERSION like 0.7.1)"
[[ -n $title ]] || die "say what is new, in a few words: scripts/release.sh $version \"…\""
need git
need gh github-cli
today=$(date +%F)
last=$(./helix --version | awk '{ print $2 }')
repo=$(gh repo view --json nameWithOwner --jq .nameWithOwner)

section "Checks"
[[ $(git branch --show-current) == main ]] || die "releases are cut from main (this is $(git branch --show-current))"
[[ -z $(git status --porcelain --untracked-files=no) ]] || die "there are uncommitted changes: commit or stash them first"
git fetch -q origin
[[ $(git rev-parse HEAD) == "$(git rev-parse origin/main)" ]] || die "main isn't what is on GitHub: push or pull first"
git rev-parse -q --verify "refs/tags/v$version" >/dev/null && die "v$version is already tagged"
[[ $(printf '%s\n%s\n' "$last" "$version" | sort -V | tail -1) == "$version" && $version != "$last" ]] \
  || die "$version isn't newer than $last"
grep -q '^## \[Unreleased\]$' CHANGELOG.md || die "CHANGELOG.md has no [Unreleased] section"
unreleased=$(awk '/^## \[Unreleased\]$/ { on = 1; next } on && /^## \[/ { exit } on && /[^[:space:]]/' CHANGELOG.md)
[[ -n $unreleased ]] || die "CHANGELOG.md's [Unreleased] section is empty: nothing to release"
grep -q "^\[Unreleased\]: .*/compare/v$last\.\.\.HEAD$" CHANGELOG.md || die "CHANGELOG.md's [Unreleased] link doesn't compare from v$last"
python3 -m unittest discover -s tests >/dev/null 2>&1 || die "the tests fail: python3 -m unittest discover -s tests"
# The Linux window runs Ventoy's installer as root only if it knows that archive's checksum
ventoy=$(./helix ventoy-path 2>/dev/null | xargs -r basename) || ventoy=''
[[ -z $ventoy ]] || grep -q "\"$ventoy-linux.tar.gz\": \"[0-9a-f]\{64\}\"" linux/helix_gui.py \
  || die "linux/helix_gui.py doesn't list $ventoy: add its sha256 (from Ventoy's release page) to VENTOY_SHA256"
ok "main is clean and pushed, the tests pass, $last → $version"

section "Version $version"
sed -i "s/^__version__ = \"$last\"$/__version__ = \"$version\"/" helix
[[ $(./helix --version | awk '{ print $2 }') == "$version" ]] || die "couldn't set the version in helix"
sed -i -e "s/^## \[Unreleased\]$/## [Unreleased]\n\n## [$version] - $today/" \
  -e "s#^\[Unreleased\]: \(.*\)/compare/v$last\.\.\.HEAD\$#[Unreleased]: \1/compare/v$version...HEAD\n[$version]: \1/compare/v$last...v$version#" CHANGELOG.md
sed -i "s/^\(| .*\) | next |$/\1 | $version |/" README.md        # the roadmap's Shipped rows that waited for this
GITHUB_REPOSITORY=$repo scripts/release-notes.sh "$version"
echo
git --no-pager diff --stat
if ((!yes)); then
  read -r -p "Release $version: $title — commit, tag and push? [y/N] " answer
  [[ $answer == [yY]* ]] || { git checkout -q -- helix CHANGELOG.md README.md; die "left as it was: nothing committed"; }
fi
git add helix CHANGELOG.md README.md
git commit -q -m "Release $version: $title"
git tag -a "v$version" -m "Helix Boot $version"
git push -q origin main
git push -q origin "v$version"
ok "v$version is tagged and pushed"

section "The build on GitHub"
info "waiting for the release build (a few minutes) …"
run=''
for _ in {1..30}; do
  run=$(gh run list --workflow windows --branch "v$version" --limit 1 --json databaseId --jq '.[0].databaseId // empty')
  [[ -n $run ]] && break
  sleep 5
done
[[ -n $run ]] || die "GitHub didn't start the release build for v$version: see https://github.com/$repo/actions"
gh run watch "$run" --exit-status >/dev/null || die "the release build failed: gh run view $run --log-failed"
files=$(gh release view "v$version" --json assets --jq '[.assets[].name] | join(", ")')
[[ $files == *HelixBoot.exe* ]] || die "v$version was published without HelixBoot.exe ($files)"
ok "v$version is published: $files"
info "https://github.com/$repo/releases/tag/v$version"

((do_pack)) && pack
ok "Released $version."
