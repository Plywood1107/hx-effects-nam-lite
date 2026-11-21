#!/bin/sh
# Run HX Edit with usblog.dylib injected; every libusb call goes to usblog/<time>-hxedit.txt.
# HX Edit has the hardened runtime but allows DYLD_ variables and unsigned libraries (its entitlements), and it
# ships its own libusb-1.0.0.dylib, which usblog interposes by name. HX Edit behaves exactly as normal.
# Use it for what you want recorded (e.g. import one IR into one slot), then quit it.
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
APP=${HX_EDIT:-"/Applications/Line6/HX Edit.app"}
LIB="$HERE/usblog_hxedit.dylib"   # universal (HX Edit runs natively on Apple Silicon), linked to HX Edit's libusb
if [ ! -f "$LIB" ]; then
  clang -arch x86_64 -arch arm64 -dynamiclib -O1 -Wall -o "$LIB" "$HERE/usblog.c" "$APP/Contents/MacOS/libusb-1.0.0.dylib"
  codesign -f -s - "$LIB" >/dev/null 2>&1 || true
fi
mkdir -p "$ROOT/usblog"
LOG="$ROOT/usblog/$(date +%Y%m%d-%H%M%S)-hxedit.txt"
if pgrep -xq "HX Edit"; then echo "HX Edit is already running: quit it first."; exit 1; fi
if pgrep -q "Line 6 Updater"; then echo "Line 6 Updater is running: quit it first (it holds the unit)."; exit 1; fi
echo "logging to $LOG"
USBLOG="$LOG" DYLD_INSERT_LIBRARIES="$LIB" "$APP/Contents/MacOS/HX Edit" >"$LOG.stdout" 2>&1
echo "HX Edit exited; $(wc -l < "$LOG") log lines in $LOG"
