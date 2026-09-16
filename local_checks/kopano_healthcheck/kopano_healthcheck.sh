#!/bin/bash
# Kopano Cloud Healthcheck - Autor: Marius Gielnik
out=$(docker exec e4a-exchange4all-1 healthcheck.sh 2>&1); rc=$?
failed=$(echo "$out" | sed -n 's/.*Failed: \([0-9]*\).*/\1/p' | tail -1)
count=$(echo "$out" | sed -n 's/^Count: \([0-9]*\).*/\1/p' | tail -1)
if [ $rc -ne 0 ]; then
  echo "2 Kopano_Healthcheck - healthcheck.sh exit code $rc"
elif [ "${failed:-0}" -gt 0 ]; then
  echo "2 Kopano_Healthcheck failed=$failed;1;1 $failed of $count checks failed"
else
  echo "0 Kopano_Healthcheck failed=0;1;1 all $count checks passed"
fi