#! /bin/sh -e

if [[ -z $ISO_URL ]]; then
    echo "usage: ISO_URL=https://assisted/cluster/discovery/image $(basename $0)"
    exit 1
fi

SCRIPT='coreos-redeploy.sh'
SSH_OPTS='-o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -o ConnectTimeout=10'
HOSTS=$*

for host in $HOSTS; do
    echo starting update of $host
    scp $SSH_OPTS $SCRIPT core@$host:/tmp &&
        ssh -fn $SSH_OPTS core@$host sudo /tmp/$SCRIPT $ISO_URL &
done
