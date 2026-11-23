#!/bin/sh
# deploy_pages.sh - make the website (branch gh-pages) from the current commit: web/ at the top, the preset builder in
# preset-builder/. Only committed files go up, never the working tree. Then push it: git push origin gh-pages
#
# The site was a `git subtree split --prefix web`; the preset builder lives in tools/preset-builder/ (its page finds
# flasher.js one folder up on the site), so the site is now assembled here instead, one commit on top of gh-pages.
set -e
cd "$(git rev-parse --show-toplevel)"
BUILDER="index.html preset-core.js fw-reader.js fw-catalog.js README.md"

idx="$(mktemp -d)/index"
export GIT_INDEX_FILE="$idx"
git read-tree HEAD:web
for f in $BUILDER; do
  git update-index --add --cacheinfo "100644,$(git rev-parse "HEAD:tools/preset-builder/$f"),preset-builder/$f"
done
tree=$(git write-tree)
unset GIT_INDEX_FILE
rm -rf "$(dirname "$idx")"

parent=$(git rev-parse refs/heads/gh-pages)
if [ "$tree" = "$(git rev-parse "$parent^{tree}")" ]; then
  echo "gh-pages already holds this site ($(git rev-parse --short "$parent"))"
  exit 0
fi
commit=$(git commit-tree "$tree" -p "$parent" -m "Site: setup page and preset builder from main $(git rev-parse --short HEAD)")
git update-ref refs/heads/gh-pages "$commit" "$parent"
echo "gh-pages -> $(git rev-parse --short "$commit"): $(git ls-tree -r --name-only "$commit" | wc -l | tr -d ' ') files"
