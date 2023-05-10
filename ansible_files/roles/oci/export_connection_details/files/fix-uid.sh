# Ensure our UID, which is randomly generated, is in /etc/passwd. This is required
# to be able to SSH.
if ! whoami &> /dev/null; then
    if [ -x "$(command -v nss_wrapper.pl)" ]; then
        grep -v -e ^default -e ^$(id -u) /etc/passwd > "/tmp/passwd"
        echo "${USER_NAME:-default}:x:$(id -u):0:${USER_NAME:-default} user:${HOME}:/sbin/nologin" >> "/tmp/passwd"
        export LD_PRELOAD=libnss_wrapper.so
        export NSS_WRAPPER_PASSWD=/tmp/passwd
        export NSS_WRAPPER_GROUP=/etc/group
    elif [[ -w /etc/passwd ]]; then
        echo "${USER_NAME:-default}:x:$(id -u):0:${USER_NAME:-default} user:${HOME}:/sbin/nologin" >> "/etc/passwd"
    else
        echo "No nss wrapper, /etc/passwd is not writeable, and user matching this uid is not found."
        exit 1
    fi
fi
