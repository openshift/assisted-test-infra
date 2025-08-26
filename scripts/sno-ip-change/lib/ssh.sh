#!/usr/bin/env bash

set -euo pipefail

# Function: _build_ssh_opts
# Purpose: Construct a common set of ssh options based on inputs.
# Parameters:
# - $1: port
# - $2: private key path
# - $3: StrictHostKeyChecking (yes|no)
_build_ssh_opts() {
	local port="$1"
	local key="$2"
	local strict_chk="$3"
	local -a opts
	opts=(-p "$port" -o StrictHostKeyChecking="$strict_chk" -o UserKnownHostsFile=/dev/null -o ServerAliveInterval=30 -o ServerAliveCountMax=5 -o LogLevel=ERROR)
	if [[ -n "$key" && -f "$key" ]]; then
		opts+=(-i "$key")
	fi
	printf '%s\n' "${opts[@]}"
}

# Function: ssh_exec
# Purpose: Execute a command on a remote host via SSH.
# Parameters:
# - $1: user
# - $2: host
# - $3: port
# - $4: private key path
# - $5: StrictHostKeyChecking (yes|no)
# - $@: command to execute remotely
ssh_exec() {
	local user="$1"; shift
	local host="$1"; shift
	local port="$1"; shift
	local key="$1"; shift
	local strict_chk="$1"; shift
	local -a opts
	mapfile -t opts < <(_build_ssh_opts "$port" "$key" "$strict_chk")
	ssh "${opts[@]}" "${user}@${host}" -- "$@"
}

# Function: ssh_wait
# Purpose: Wait until a remote host is reachable via SSH.
# Parameters:
# - $1..$5: same as ssh_exec (user, host, port, key, strict)
# - $6: timeout seconds (optional, default 600)
ssh_wait() {
    local user="$1"; shift
    local host="$1"; shift
    local port="$1"; shift
    local key="$1"; shift
    local strict_chk="$1"; shift
    local timeout_secs="${1:-600}"
    local -a opts
    mapfile -t opts < <(_build_ssh_opts "$port" "$key" "$strict_chk")
    local start now
    start=$(date +%s)
    while true; do
        if ssh "${opts[@]}" -o BatchMode=yes -o ConnectTimeout=3 "${user}@${host}" -- true >/dev/null 2>&1; then
            return 0
        fi
        now=$(date +%s)
        if (( now - start > timeout_secs )); then
            echo "[$(date '+%Y-%m-%dT%H:%M:%S%z')] ERROR: Timeout waiting for SSH to ${host}:${port}" >&2
            return 1
        fi
        sleep 5
    done
}

# Function: copy_to_remote
# Purpose: Copy a file to the remote host path.
# Parameters: user, host, port, key, strict, src, dest
copy_to_remote() {
	local user="$1"; shift
	local host="$1"; shift
	local port="$1"; shift
	local key="$1"; shift
	local strict_chk="$1"; shift
	local src="$1"; shift
	local dest="$1"; shift
	local -a scpopts
	scpopts=(-q -P "$port" -o StrictHostKeyChecking="$strict_chk" -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR)
	if [[ -n "$key" && -f "$key" ]]; then
		scpopts+=(-i "$key")
	fi
	local scp_host="$host"
	if is_ipv6_address "$host"; then
		scp_host="[${host}]"
	fi
	scp "${scpopts[@]}" "$src" "${user}@${scp_host}:$dest"
}

# Function: copy_dir_to_remote
# Purpose: Copy a directory recursively to the remote host path.
# Parameters: user, host, port, key, strict, src_dir, dest_dir
copy_dir_to_remote() {
	local user="$1"; shift
	local host="$1"; shift
	local port="$1"; shift
	local key="$1"; shift
	local strict_chk="$1"; shift
	local src_dir="$1"; shift
	local dest_dir="$1"; shift
	local -a scpopts
	scpopts=(-q -r -P "$port" -o StrictHostKeyChecking="$strict_chk" -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR)
	if [[ -n "$key" && -f "$key" ]]; then
		scpopts+=(-i "$key")
	fi
	# Ensure destination directory exists on remote (user-owned)
	local -a opts
	mapfile -t opts < <(_build_ssh_opts "$port" "$key" "$strict_chk")
	ssh "${opts[@]}" "${user}@${host}" bash -s -- "$dest_dir" <<'EOS'
dest="$1"
mkdir -p -- "$dest"
EOS
	# Copy directory contents (not the directory itself)
	local scp_host="$host"
	if is_ipv6_address "$host"; then
		scp_host="[${host}]"
	fi
	scp "${scpopts[@]}" "$src_dir/." "${user}@${scp_host}:$dest_dir/"
}

# Function: prepare_remote_dir
# Purpose: Create a temporary working directory on the remote host.
# Returns: Prints remote directory path
prepare_remote_dir() {
	local user="$1"; shift
	local host="$1"; shift
	local port="$1"; shift
	local key="$1"; shift
	local strict_chk="$1"; shift
	local dir
	local -a opts
	mapfile -t opts < <(_build_ssh_opts "$port" "$key" "$strict_chk")
	dir=$(ssh "${opts[@]}" "${user}@${host}" bash -s <<'EOS'
mktemp -d
EOS
)
	printf '%s\n' "$dir"
}

# Function: detect_remote_br_ex_interface
# Purpose: Detect the interface attached to br-ex on the remote node.
# Returns: Prints interface name
detect_remote_br_ex_interface() {
	local user="$1"; shift
	local host="$1"; shift
	local port="$1"; shift
	local key="$1"; shift
	local strict_chk="$1"; shift
	local -a opts
	mapfile -t opts < <(_build_ssh_opts "$port" "$key" "$strict_chk")
	ssh "${opts[@]}" "${user}@${host}" sudo bash -s <<'EOS'
set -euo pipefail

# Prefer OVS knowledge of br-ex ports, picking a physical NIC with carrier
if command -v ovs-vsctl >/dev/null 2>&1; then
	ports=$(ovs-vsctl list-ports br-ex 2>/dev/null || true)
	best=""
	if [[ -n "$ports" ]]; then
		for p in $ports; do
			[[ "$p" == "br-ex" ]] && continue
			# Skip internal/patch interfaces
			type_val=$(ovs-vsctl get Interface "$p" type 2>/dev/null | tr -d '"' || true)
			if [[ -n "$type_val" && "$type_val" != "system" ]]; then
				continue
			fi
			# Prefer LOWER_UP
			if ip -o link show "$p" 2>/dev/null | grep -q "LOWER_UP"; then
				echo "$p"; exit 0
			fi
			# Fallback candidate
			[[ -z "$best" ]] && best="$p"
		done
		if [[ -n "$best" ]]; then
			echo "$best"; exit 0
		fi
	fi
fi

# Fallback to NetworkManager view: first connected ethernet device (not br-ex)
if command -v nmcli >/dev/null 2>&1; then
	iface=$(nmcli -t -f DEVICE,TYPE,STATE device status | awk -F: '($2=="ethernet" && $3=="connected"){print $1; exit}' || true)
	if [[ -n "$iface" && "$iface" != "br-ex" ]]; then echo "$iface"; exit 0; fi
fi

exit 1
EOS
}
