#!/usr/bin/env bash
# Snapshot + push bobgen state so nothing is lost if the box/laptop dies.
# Run every 5 min by the driver (and/or a cron loop).
set -uo pipefail
BOBGEN="$HOME/dark-factory/bobgen"
cd "$BOBGEN" || exit 1

# stamp a heartbeat (timestamp passed in as $1 to stay deterministic; else 'now')
STAMP="${1:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"
echo "$STAMP heartbeat" >> heartbeat.log

git add -A 2>/dev/null
# only commit if there is something to commit
if ! git diff --cached --quiet 2>/dev/null; then
  git -c user.email=yelkhamra@gmail.com -c user.name=yelkhamr \
      commit -q -m "bobgen state $STAMP" 2>/dev/null
fi

# push to the dedicated state branch if a remote is configured
if git remote get-url origin >/dev/null 2>&1; then
  TOKEN="$(grep -h '^export GITHUB_TOKEN=' "$HOME/.zshrc" "$HOME/.bashrc" 2>/dev/null | tail -1 | cut -d= -f2)"
  if [ -n "${TOKEN:-}" ]; then
    git push "https://${TOKEN}@github.com/yye00/bob.git" HEAD:refs/heads/bobgen-state -f 2>/dev/null \
      && echo "$STAMP pushed" >> heartbeat.log \
      || echo "$STAMP push-failed" >> heartbeat.log
  fi
fi
