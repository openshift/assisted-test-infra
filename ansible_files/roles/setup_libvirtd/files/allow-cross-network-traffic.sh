#!/usr/bin/env sh
(
    flock 3
    iptables -S | grep -E "LIBVIRT_FW[IO] .* REJECT" | sed -e 's/^-A/iptables -D/g' -e 's/$/ || true/g' | sh
) 3>/tmp/iptables.lock
