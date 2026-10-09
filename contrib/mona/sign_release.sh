#!/bin/bash
#
# Sign release files with GPG: one detached, ascii-armored signature per file (<file>.asc),
# as for earlier Electrum-MONA releases. Run this on the machine that holds the release key.
#
# usage:
#   contrib/mona/sign_release.sh <directory>      sign the files in <directory>
#   contrib/mona/sign_release.sh --run <run id>   download the artifacts of a run of the "builds"
#                                                 workflow with gh first (into dist-release/<run id>)
#
# env:
#   GPG_KEY   key to sign with (default: the release key in pubkeys/wakiyamap.asc)
#   GH_REPO   repository to download from (default: wakiyamap/electrum-mona)

set -e

GPG_KEY="${GPG_KEY:-315525E811D5E586F3CAC0329C740BEC897CE499}"
GH_REPO="${GH_REPO:-wakiyamap/electrum-mona}"

fail() { echo "error: $*" >&2; exit 1; }

if [ "$1" = "--run" ]; then
    [ -n "$2" ] || fail "usage: $0 --run <run id>"
    command -v gh > /dev/null || fail "gh (GitHub CLI) is needed for --run"
    DIR="dist-release/$2"
    [ ! -e "$DIR" ] || fail "$DIR already exists"
    mkdir -p "$DIR"
    gh run download "$2" --repo "$GH_REPO" --dir "$DIR/.artifacts"
    # gh puts each artifact into its own folder: collect the files
    find "$DIR/.artifacts" -type f -exec mv -n {} "$DIR/" \;
    [ -z "$(find "$DIR/.artifacts" -type f)" ] || fail "two artifacts contain a file with the same name, see $DIR/.artifacts"
    rm -r "$DIR/.artifacts"
elif [ -d "$1" ]; then
    DIR="$1"
else
    fail "usage: $0 <directory> | --run <run id>"
fi

command -v gpg > /dev/null || fail "gpg not found"
gpg --list-secret-keys "$GPG_KEY" > /dev/null 2>&1 || fail "no secret key for $GPG_KEY in the gpg keyring (set GPG_KEY?)"

count=0
for f in "$DIR"/*; do
    [ -f "$f" ] || continue
    case "$f" in *.asc|*.sig) continue ;; esac
    gpg --local-user "$GPG_KEY" --armor --detach-sign --yes --output "$f.asc" "$f"
    gpg --verify "$f.asc" "$f" > /dev/null 2>&1 || fail "the signature of $f does not verify"
    count=$((count + 1))
done
[ "$count" -gt 0 ] || fail "no files to sign in $DIR"

echo "signed $count files in $DIR:"
( cd "$DIR" && for f in *; do case "$f" in *.asc|*.sig) ;; *) [ -f "$f" ] && sha256sum "$f" ;; esac; done )
echo
echo "to attach them to a release:"
echo "  gh release upload <tag> \"$DIR\"/* --repo $GH_REPO"
