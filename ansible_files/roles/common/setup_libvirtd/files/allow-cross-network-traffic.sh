#!/usr/bin/env sh
(
    flock 3
    iptables-save -c | grep -E -v 'LIBVIRT_FW[IO] .* REJECT' >/tmp/iptables.txt
    iptables-restore </tmp/iptables.txt
    rm /tmp/iptables.txt
) 3>/tmp/iptables.lock
