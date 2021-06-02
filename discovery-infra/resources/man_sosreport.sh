#!/bin/bash
export LANG=C

# If this script hangs, un-comment the below two entries and note the command that the script hangs on.  Then comment out that command and re-run the script.
# set -x
# set -o verbose

[[ -d /tmp/sosreport ]] && rm -rf /tmp/sosreport
mkdir /tmp/sosreport && cd /tmp/sosreport && mkdir -p  var/log etc/lvm etc/sysconfig network storage sos_commands/networking

echo -e "Gathering system information..."
hostname &> hostname
cp -a /etc/redhat-release  ./etc/ 2>> error_log
uptime &> uptime

echo -e "Gathering application information..."
chkconfig --list &> chkconfig
top -bn1 &> top_bn1
service --status-all &> service_status_all
date &> date
ps auxww &> ps_auxww
ps -elf &> ps_-elf
rpm -qa --last &> rpm-qa
echo -e "Running 'rpm -Va'. This may take a moment."
rpm -Va &> rpm-Va

echo -e "Gathering memory information..."
free -m &> free
vmstat 1 10 &> vmstat

echo -e "Gathering network information..."
ifconfig &> ./network/ifconfig
netstat -s &>./network/netstat_-s
netstat -agn &> ./network/netstat_-agn
netstat -neopa &> ./network/netstat_-neopa
route -n &> ./network/route_-n
for i in $(ls /etc/sysconfig/network-scripts/{ifcfg,route,rule}-*) ; do echo -e "$i\n----------------------------------"; cat $i;echo " ";  done &> ./sos_commands/networking/ifcfg-files
for i in $(ifconfig | grep "^[a-z]" | cut -f 1 -d " "); do echo -e "$i\n-------------------------" ; ethtool $i; ethtool -k $i; ethtool -S $i; ethtool -i $i;echo -e "\n" ; done &> ./sos_commands/networking/ethtool.out
cp /etc/sysconfig/network ./sos_commands/networking/ 2>> error_log
cp /etc/sysconfig/network-scripts/ifcfg-* ./sos_commands/networking/ 2>> error_log
cp /etc/sysconfig/network-scripts/route-* ./sos_commands/networking/ 2>> error_log
cat /proc/net/bonding/bond* &> ./sos_commands/networking/proc-net-bonding-bond 2>> error_log
iptables --list --line-numbers &> ./sos_commands/networking/iptables_--list_--line-numbers
ip route show table all &> ./sos_commands/networking/ip_route_show_table_all
ip link &> ./sos_commands/networking/ip_link

echo -e "Gathering Storage/Filesystem information..."
df -l &> df
fdisk -l &> fdisk
parted -l &> parted
cp -a /etc/fstab  ./etc/ 2>> error_log
cp -a /etc/lvm/lvm.conf ./etc/lvm/ 2>> error_log
cp -a /etc/lvm/backup/ ./etc/lvm/ 2>> error_log
cp -a /etc/lvm/archive/ ./etc/lvm/ 2>> error_log
cp -a /etc/multipath.conf ./etc/ 2>> error_log
cat /proc/mounts &> mount
iostat -tkx 1 10 &> iostat_-tkx_1_10
parted -l &> storage/parted_-l
vgdisplay -v &> storage/vgdisplay
lvdisplay &> storage/lvdisplay
pvdisplay &> storage/pvdisplay
pvs -a -v &> storage/pvs
vgs -v &> storage/vgs
lvs -o +devices &> storage/lvs
multipath -v4 -ll &> storage/multipath_ll
pvscan -vvvv &> storage/pvscan
vgscan -vvvv &> storage/vgscan
lvscan -vvvv &> storage/lvscan
lsblk &> storage/lsblk
lsblk -t &> storage/lsblk_t
dmsetup info -C &> storage/dmsetup_info_c
dmsetup status &>  storage/dmsetup_status
dmsetup table &>  storage/dmsetup_table
ls -lahR /dev &> storage/dev

echo -e "Gathering kernel information..."
cp -a /etc/security/limits.conf ./etc/ 2>> error_log
cp -a /etc/sysctl.conf ./etc/ 2>> error_log
ulimit -a &> ulimit
cat /proc/slabinfo &> slabinfo
cat /proc/interrupts &> interrupts
cat /proc/iomem &> iomem
cat /proc/ioports &> ioports
slabtop -o &> slabtop_-o
uname -a &> uname
sysctl -a &> sysctl_-a
lsmod &> lsmod
cp -a /etc/modprobe.conf ./etc/ 2>> error_log
cp -a  /etc/sysconfig/* ./etc/sysconfig/ 2>> error_log
for MOD in `lsmod | grep -v "Used by"| awk '{ print $1 }'`; do modinfo  $MOD 2>&1 >> modinfo; done;
ipcs -a &> ipcs_-a
ipcs -s | awk '/^0x/ {print $2}' | while read semid; do ipcs -s -i $semid; done &> ipcs_-s_verbose
sar -A &> sar_-A
cp -a /var/log/dmesg dmesg 2>> error_log
dmesg &> dmesg_now

echo -e "Gathering hardware information..."
dmidecode &> dmidecode
lspci -vvv &> lspci_-vvv
lspci &> lspci
cat /proc/meminfo &> meminfo
cat /proc/cpuinfo &> cpuinfo

echo -e "Gathering kdump information..."
cp -a /etc/kdump.conf ./etc/ 2>> error_log
ls -laR /var/crash &> ls-lar-var-crash
ls -1 /var/crash | while read n; do mkdir -p var/crash/${n}; cp -a /var/crash/${n}/vmcore-dmesg* var/crash/${n}/ 2>> error_log; done

echo -e "Gathering container related information..."
mkdir container
rpm -q podman || alias podman="docker"
podman ps &> container/ps
podman image list &> container/image_list
podman ps | awk '$1!="CONTAINER" {print $1}' | while read id; do podman inspect $id &> container/inspect_${id}; done

echo -e "Gathering logs..."
cp -a /var/log/{containers*,message*,secure*,boot*,cron*,yum*,Xorg*,sa,rhsm,audit,dmesg} ./var/log/ 2>> error_log
cp -a /etc/*syslog.conf ./etc/ 2>> error_log
journalctl -u kubelet.service > ./var/log/kubelet.log 2>> error_log
journalctl -u bootkube.service > ./var/log/bootkube.log 2>> error_log
journalctl -u crio.service > ./var/log/crio.log 2>> error_log

echo -e "Gathering Openshift data..."
export KUBECONFIG=/etc/kubernetes/bootstrap-secrets/kubeconfig
oc describe clusteroperators &> clusteroperators
oc describe clusterversion &> clusterversion
oc describe nodes &> nodes

echo -e "Compressing files..."
tar -cjhf /tmp/sosreport.tar.bz2 ./

echo -e "Script complete."
