#!/bin/sh
cd /home/john-riley/.cache/quanthaxs-data-push-public-proof-20261004-v1 || exit 98
python3 -u probe.py > probe.log 2>&1
result=$?
printf 'EXIT_CODE:%s\n' "$result" >> probe.log
