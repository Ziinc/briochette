#!/usr/bin/env bash
# Installs a simulator build of the counter, launches it, checks the
# embedded CPython starts and draws the first frame, taps Increment where
# the host logged it (with idb), and waits for the app's own log line.
#
#   scripts/ios-smoke.sh <path/to/app> <bundle id> [out-dir]
set -euo pipefail

app=${1:?usage: ios-smoke.sh <path/to/app> <bundle id> [out-dir]}
bundle=${2:?usage: ios-smoke.sh <path/to/app> <bundle id> [out-dir]}
out=$(mkdir -p "${3:-ios-smoke}" && cd "${3:-ios-smoke}" && pwd)
log=$out/app.log
exe=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleExecutable' "$app/Info.plist")

device=$(xcrun simctl list devices available -j |
  jq -r '[.devices | to_entries[] | select(.key | test("iOS")) | .value[]
          | select(.name | startswith("iPhone"))][0].udid // empty')
[ -n "$device" ] || { echo "FAIL: no iPhone simulator is available"; exit 1; }
echo "ios-smoke: using simulator $device"
xcrun simctl boot "$device" 2>/dev/null || true
xcrun simctl bootstatus "$device" -b >/dev/null
xcrun simctl install "$device" "$app"

since=$(date '+%Y-%m-%d %H:%M:%S')
sleep 1
xcrun simctl launch --terminate-running-process "$device" "$bundle"

sync_log() {
  xcrun simctl spawn "$device" log show --style compact --info --debug --start "$since" \
    --predicate "process == \"$exe\"" >"$log" 2>&1 || true
}

fail() {
  sync_log
  echo "FAIL: $*"
  xcrun simctl io "$device" screenshot "$out/failure.png" >/dev/null 2>&1 || true
  cp ~/Library/Logs/DiagnosticReports/"$exe"*.ips "$out/" 2>/dev/null || true
  grep -E '\[(stdout|stderr)\]|levain|counter|Traceback|Error' "$log" | tail -80 || true
  exit 1
}

wait_for() {
  local deadline=$((SECONDS + $2))
  while ((SECONDS < deadline)); do
    sync_log
    grep -Eq "$1" "$log" && return 0
    sleep 1
  done
  fail "no line matching /$1/ within $2 s"
}

tap() {
  local at
  at=$(grep -Eo "levain: bounds $1 [0-9]+ [0-9]+" "$log" | tail -1 | cut -d' ' -f4-)
  [ -n "$at" ] || fail "no bounds logged for $1"
  echo "tap $1 at $at"
  # shellcheck disable=SC2086
  idb ui tap --udid "$device" $at
}

wait_for 'levain: app at' 120
wait_for 'levain: first frame' 120
sleep 2
xcrun simctl io "$device" screenshot "$out/first-frame.png" >/dev/null
command -v idb >/dev/null || fail "idb is not installed"
wait_for 'levain: bounds Increment [0-9]+ [0-9]+' 30
tap Increment
wait_for 'counter: count=1' 30
tap Increment
wait_for 'counter: count=2' 30
xcrun simctl io "$device" screenshot "$out/tapped.png" >/dev/null
echo "PASS: CPython runs the counter on iOS and taps reach it"
