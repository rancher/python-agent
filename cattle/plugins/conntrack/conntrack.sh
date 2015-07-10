#!/bin/bash
set -e

watch()
{
    conntrack -E -p udp --dport=$1 --sport=$1 | sed -E 's/.*src=(.*)dst=.*dport=(.*)src=.*dst=(.*)sport=.*dport=([^ ]* ).*/\1\2\3\4/g' | while read IP_SRC PORT_SRC IP_DST PORT_DST; do
    if [ "$PORT_DST" == "$PORT_SRC" ] && [ "$IP_SRC" != "$IP_DST" ]; then
        echo Bad rule $IP_SRC $PORT_SRC $IP_DST $PORT_DST
        conntrack -L
        iptables -L -t nat
        conntrack -D -p udp --dport=$1 --sport=$1 || true
    fi
done
}

watch 500 &
watch 4500 &

sleep 1

conntrack -D -p udp --dport=500 --sport=500 || true
conntrack -D -p udp --dport=4500 --sport=4500 || true

wait
exit 1
