#!/usr/bin/env bash
# Installs the counter APK on a running emulator, checks the embedded
# CPython starts and draws the first frame, taps Increment where the host
# logged it, and waits for the app's own log line. Saves logcat and
# screenshots to the output directory.
#
#   scripts/android-smoke.sh counter.apk <package> [out-dir]
set -euo pipefail

APK=$1
PKG=$2
OUT=${3:-android-smoke}
mkdir -p "$OUT"
ADB_BIN=$(command -v adb)
# Bound every adb call so a wedged device fails the run instead of hanging it.
adb() { timeout 90 "$ADB_BIN" "$@"; }

timeout 300 "$ADB_BIN" wait-for-device
adb shell settings put global hide_error_dialogs 1 || true
adb install -r -g "$APK"
adb shell am wait-for-broadcast-idle || sleep 5
adb logcat -c
"$ADB_BIN" logcat >"$OUT/logcat.txt" 2>&1 &
logcat=$!
trap 'adb exec-out screencap -p >"$OUT/final.png" || true; kill "$logcat" 2>/dev/null || true' EXIT
adb shell am start -n "$PKG/.MainActivity"

# wait_for <regex> <seconds>: waits for a logcat line.
wait_for() {
  local deadline=$((SECONDS + $2))
  while ((SECONDS < deadline)); do
    grep -Eq "$1" "$OUT/logcat.txt" && return 0
    sleep 1
  done
  echo "FAIL: no logcat line matching /$1/ within $2 s"
  grep -E 'levain|python|counter|Traceback|Error' "$OUT/logcat.txt" | tail -60 || true
  exit 1
}

# tap <label>: taps the centre the host logged for the control, in pixels.
tap() {
  local at
  at=$(grep -Eo "levain: bounds $1 [0-9]+ [0-9]+" "$OUT/logcat.txt" | tail -1 | cut -d' ' -f4-)
  [ -n "$at" ] || { echo "FAIL: no bounds logged for $1"; exit 1; }
  echo "tap $1 at $at"
  # shellcheck disable=SC2086
  adb shell input tap $at
}

wait_for 'levain: app at' 120
wait_for 'levain: first frame' 120
sleep 2
adb exec-out screencap -p >"$OUT/first-frame.png"
wait_for 'levain: bounds Increment [0-9]+ [0-9]+' 30
tap Increment
wait_for 'counter: count=1' 30
tap Increment
wait_for 'counter: count=2' 30
adb exec-out screencap -p >"$OUT/tapped.png"
echo "PASS: CPython runs the counter on Android and taps reach it"
