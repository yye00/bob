#!/usr/bin/env bash
# Launch the autonomous bobgen driver in a detached tmux session.
# DO NOT run until hippy/hipsci is finished (Phase 0 gate).
set -euo pipefail
BOBGEN="$HOME/dark-factory/bobgen"
export PATH="$HOME/.local/bin:$HOME/.local/node/bin:$PATH"

# Guard: refuse to start if a hippy/hipsci build is still running.
if tmux has-session -t build 2>/dev/null; then
  echo "REFUSING: hippy/hipsci 'build' tmux session still active. Finish Phase 0 first."
  exit 1
fi

if tmux has-session -t bobgen 2>/dev/null; then
  echo "bobgen session already running. Attach with: tmux attach -t bobgen"
  exit 0
fi

# Launch claude as the autonomous driver, seeded with the driver instructions.
# --dangerously-skip-permissions so it runs unattended; guardrail lives in the prompt.
tmux new-session -d -s bobgen "cd $HOME/dark-factory && \
  source $HOME/dark-factory/bob/bob_build.env && \
  claude --dangerously-skip-permissions \
    \"Read $BOBGEN/bobgen-driver.md and follow it exactly. You are the autonomous bobgen driver. Obey the HARD GUARDRAIL: never lower any acceptance-criteria/confidence threshold. Begin Phase 2: build bob96 using bob95. Write state to $BOBGEN every 5 minutes and run $BOBGEN/bobgen-state-push.sh after each write.\" \
    > $BOBGEN/driver.log 2>&1"
echo "bobgen driver launched in tmux session 'bobgen'. Log: $BOBGEN/driver.log"
