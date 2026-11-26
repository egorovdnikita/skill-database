#!/bin/bash
# Устанавливает скилл database для локального Claude Code и включает автообновление из GitHub.
set -e
DEST="$HOME/.claude/skills/database"
REPO="https://github.com/egorovdnikita/skill-database.git"
mkdir -p "$HOME/.claude/skills"
if [ -d "$DEST/.git" ]; then
  git -C "$DEST" pull --ff-only
else
  [ -e "$DEST" ] && mv "$DEST" "$DEST.bak.$(date +%s)"
  git clone "$REPO" "$DEST"
fi
PL="$HOME/Library/LaunchAgents/com.egorovdnikita.skill-database.plist"
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PL" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.egorovdnikita.skill-database</string>
  <key>ProgramArguments</key><array><string>/bin/sh</string><string>-c</string><string>/usr/bin/python3 -I "$DEST/scripts/sync-skills.py" sync</string></array>
  <key>StartInterval</key><integer>1800</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardErrorPath</key><string>/tmp/skill-database-sync.log</string>
</dict></plist>
PLIST
launchctl unload "$PL" 2>/dev/null || true
launchctl load "$PL"
echo "Готово: $DEST, автообновление каждые 30 минут."
