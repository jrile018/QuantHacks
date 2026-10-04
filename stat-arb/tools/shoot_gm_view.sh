#!/bin/bash
# Lives in tools/ rather than a scratch directory because a GUI that can
# only be verified by a person remembering to look is a GUI that quietly
# breaks; this is the repeatable way to get a screenshot out of gm-view.
# Launch gm-view against ONE run and capture just its window.
#
# A GUI that can only be checked by a person remembering to look is a GUI
# that quietly breaks between releases; this is how every screenshot in
# this work was produced, and it is repeatable by anyone.
#
# The run is symlinked into a directory of its own because gm-view loads
# every run under the directory it is given and opens the first - pointing
# it at runs/ would show whichever run sorts first, not the one asked for.
#
# The capture is cropped to gm-view's own window rather than the whole
# root display: this is somebody's real desktop, and their other windows
# are not part of the deliverable.
#
# usage: shoot.sh <out.png> <run_dir> [gm-view args...]
set -u
OUT="$1"; shift
RUN="$1"; shift

export DISPLAY=:0
cd ~/projects/geomarket || exit 1

STAGE=/tmp/shoot-runs
rm -rf "$STAGE"
mkdir -p "$STAGE"
ln -s "$(readlink -f "$RUN")" "$STAGE/$(basename "$RUN")"

pkill -x gm-view 2>/dev/null
sleep 1

./build/linux-gcc-release/bin/gm-view "$STAGE" "$@" > /tmp/gmview.log 2>&1 &
VIEWPID=$!
# The viewer reads scores.parquet (1.8M rows on a full run) before its
# first frame; too short a wait captures an empty window, which looks
# exactly like a rendering failure.
sleep 30

if ! kill -0 "$VIEWPID" 2>/dev/null; then
  echo "gm-view exited before capture:"
  tail -20 /tmp/gmview.log
  exit 1
fi

# gm-view's own window id. Capturing the root and cropping by the
# geometry xwininfo prints in -tree does not work under a reparenting
# window manager: those coordinates are relative to the frame's parent,
# not the screen, so the crop lands on whatever happens to be at the
# top-left of the desktop. Ask X for the window itself instead.
WINID=$(xwininfo -root -tree 2>/dev/null | grep -i 'gm-view' | grep -oE '0x[0-9a-f]+' | head -1)

if [ -n "$WINID" ]; then
  echo "capturing gm-view window $WINID"
  xwd -id "$WINID" -silent > /tmp/shot.xwd || { echo "xwd failed"; exit 1; }
else
  echo "WARNING: gm-view window not found; capturing the whole root display"
  xwd -root -silent > /tmp/shot.xwd || { echo "xwd failed"; exit 1; }
fi
ffmpeg -y -loglevel error -i /tmp/shot.xwd "$OUT"
echo "captured $OUT"
tail -3 /tmp/gmview.log
pkill -x gm-view 2>/dev/null
exit 0
