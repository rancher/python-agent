#!/bin/bash
set -e

# This is a band-aid and just here to help narrow down the root cause

check()
{
    if conntrack  -L -p udp --dport $1 --sport $1 2>/dev/null | grep UNREPLIED; then
       if [ "$2" = "delete" ]; then
           echo Deleting conntrack rule for port $1
           conntrack -D -p udp --dport $1 --sport $1 || true
       else
           return 1
       fi
    fi
}

while sleep 1; do
    for i in 500 4500; do
        if ! check $i; then
            sleep 2
            check  $i || check $i delete
        fi
    done
done
