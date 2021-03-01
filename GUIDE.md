# Assisted Installer Unofficial Install Guide

## Prerequisites

1. Install CentOS8/RHEL8 on the assisted installer host<sup id="a1">[1](#f1)</sup>
   - This host will run minikube and the UI for deploying OpenShift on Bare Metal
1. Setup DHCP/DNS records for the following OpenShift nodes and VIPs. List includes
   - Master nodes
   - Worker nodes
   - API VIP
   - Ingress VIP
     > NOTE: dnsmasq can be used to setup [DHCP](https://openshift-kni.github.io/baremetal-deploy/4.4/Deployment.html#creating-dhcp-reservations-using-dnsmasq-option2_ipi-install-prerequisites) and [DNS](https://openshift-kni.github.io/baremetal-deploy/4.4/Deployment.html#creating-dns-records-using-dnsmasq-option2_ipi-install-prerequisites). Out of scope for this document but I've included links on how to do it.
1. Ensure these values are properly set via `nslookup` and dig commands from your assisted installer host
1. Download your Pull Secret from https://cloud.redhat.com/openshift/install/metal/user-provisioned

## Deployment

Procedure

As `$USER` user with `sudo` privileges,

1.  Generate an SSH key if not already available (`ssh_key/key`)

        [$USER@assisted_installer ~]# ssh-keygen -t rsa -f ~/.ssh/id_rsa -P ''

1.  Install git and make on your assisted installer host if not already present. Note that repositories should be already configured and available on your system.

        [$USER@assisted_installer ~]# dnf install -y make git

1.  Create a directory under `~/` labeled `assisted-installer` and `git clone` the `test-infra` git repository

        [$USER@assisted_installer ~]# mkdir ~/assisted-installer
        [$USER@assisted installer assisted-installer]# cd ~/assisted-installer/
        [$USER@assisted_installer assisted-installer]# git clone https://github.com/openshift/assisted-test-infra
        [$USER@assisted_installer assisted-installer]# cd assisted-test-infra

1.  Setup the assisted installer's environment by running the `install_environment.sh` script

        [$USER@assisted_installer assisted-test-infra]# ./scripts/install_environment.sh

1.  Once complete, run the `create_full_environment` using `make`

        [$USER@assisted_installer assisted-test-infra]# make create_full_environment

1.  **(Optional)** Currently the Installer defaults to deploying OpenShift 4.7. If you wish to change this value, set `OPENSHIFT_VERSION` to a different value, e.g. 4.6, 4.8

        [$USER@assisted_installer assisted-test-infra]# export OPENSHIFT_VERSION=4.7

1.  Once complete, run the "run" using make that creates the `assisted-service` and deploys the UI

        [$USER@assisted_installer assisted-test-infra]# make run
        .
        .
        .


        deploy_ui.sh: OCP METAL UI can be reached at http://<host-ip>:6008
        deploy_ui.sh: Done

1. Once the UI has finished deploying, on a browser, access it via your host's IP and use port 6008, URL will be something like `http://<host-ip>:6008`

1. Within the browser, select the `Create New Cluster` blue button

1. A popup window labeled `New Bare Metal OpenShift Cluster` opens and requests a Cluster Name and OpenShift Version. Enter an appropriate Cluster Name.

   > NOTE: The OpenShift Version selected is the value assigned to `OPENSHIFT_VERSION` (defaults to 4.7)

1. On the next screen, enter the **Base DNS Domain**, **Pull Secret**, and **SSH Public Key**. Once complete, click on the button **Validate & Save Changes**.


    - The **Base DNS Domain** would be something like example.com.
    - The **pull secret** would be the file contents you captured as a prerequisite.
    - The **SSH public key** would be the file contents of `~/.ssh/id_rsa.pub`

    > NOTE: This screen also shows Available subnets, API Virtual IP and Ingress VIP but these do not need to be set at this time of the install.

    > NOTE: If you get `Value must be valid JSON` for your pull secret, make sure you are not surrounding your pull secret in tick marks `' '`

    > NOTE: Make sure to delete any extra white spaces when entering your pull secret and SSH key.

1. Once **Validate & Save Changes** has been clicked, click on the blue button labeled **Download discovery ISO**, and enter the HTTP Proxy URL (if required) and SSH public key using the host that is serving out the assisted installer UI. Click **Download Discovery ISO**. This will prepare the ISO and start the download

   > NOTE: If you wish not to download the ISO on your current system but on a separate system, after you've initiated the download by clicking the button, you can cancel the download and run the following `wget` command.


    > NOTE: This example installs ISO on the assisted installer host that will serve out the ISO via HTTP for the OpenShift cluster nodes.

        [$USER@assisted_installer ~]# mkdir ~/assisted-installer/images
        [$USER@assisted_installer ~]# wget http://$(hostname):6008/api/assisted-install/v1/clusters/<cluster-id>/downloads/image -O ~/assisted-installer/images/live.iso

    > NOTE: When the ISO starts the initial download the cluster ID will show up on your browser address bar. Use that value and replace `<cluster-id>` with it.

1. The next step uses [Juan Parrilla's git repository](https://github.com/jparrill/racadm-image) for simplicity to do the following:

   - Create a `podman` container that will setup `iDRAC` on DELL servers to boot from ISO

   > NOTE: Steps 14-18 only work on DELL hardware. A different method would need to be used if using a different vendor to mount your live ISO.

1)  Create a web server container labeled `mywebserver` that is to serve the `live.iso` from the `~/assisted-installer/images` directory serving out of port 8080 as follows

        [$USER@assisted_installer ~]# firewall-cmd --add-port=8080/tcp --zone=public --permanent
        [$USER@assisted_installer ~]# firewall-cmd --reload
        [$USER@assisted_installer ~]# podman run -d --name mywebserver -v ~assisted-installer/images/:/var/www/html:Z -p 8080:8080/tcp registry.centos.org/centos/httpd-24-centos7:latest

    > NOTE: Verify you can access the live.iso link as such http://<host-ip>:8080/live.iso

1. Clone the repository as follows


        ~~~sh
        [$USER@assisted_installer ~]# cd ~/assisted-installer

        [$USER@assisted_installer assisted-installer]# git clone https://github.com/jparrill/racadm-image.git
        ~~~

1.  Change into the `racadm-image` directory and build the Dockerfile using `podman`. This will create an podman container that will be used to mount the live.iso to your baremetal nodes via iDRAC.

        [$USER@assisted_installer assisted-installer]# cd racadm-image
        [$USER@assisted_installer racadm-image]# podman build . -t idracbootfromiso

    > NOTE: Ignore any errors and just ensure your `idracbootfromiso` image is created and exists under the command podman images. If it failed, please attempt to re-run the command above.

1.  With the `idracbootfromiso` image created, we will now use it to mount the `live.iso` on all of our OpenShift nodes. For simplicity, this example shows 3 servers (3 masters, 0 workers) but can be extended to X number of servers requiring the `live.iso`

        [$USER@assisted_installer ~]# for i in <master0-idrac-ip> <master1-idrac-ip> <master2-idrac-ip>; do podman run --net=host idracbootfromiso -r $i -u <idrac-user> -p "<idrac-pw>" -i http://       <host-ip>:8080/live.iso; done

    > NOTE1: Ensure to include the proper host **iDRAC IPs**, **iDRAC user** and **iDRAC password**. This for loop assumes iDRAC user and iDRAC password are the same, if different adjust the shell command accordingly.


    > NOTE2: Also make sure to **remove/eject the older ISO** which were mounted using `racadm` command as shown below

        sshpass -p '*****' ssh root@<iDRAC-IP> racadm remoteimage -d

1.  The `live.iso` should reboot the nodes and boot them into a Fedora Live image. Once it has done this, shortly you will notice the nodes becoming discoverable for your cluster via the `http://<host-ip>:6008/clusters/<cluster-id>` dashboard.

1.  Once the nodes are now available on the dashboard, select the appropriate role for each OpenShift cluster node.

1.  Enter the API Virtual VIP that you assigned via DNS.

1.  Enter the Ingress VIP that you assigned via DNS.

    > NOTE: More Network Configuration changes can be made such as changing **Cluster Network CIDR**, **Cluster Network Host Prefix**, **Service Network CIDR** if you change the **Network Configuration** from **Basic** to **Advanced**.

1.  Click the **Validate & Save** Changes button.

1.  The blue button to **Install Cluster** should now be made available. Select it.

1.  Wait for the installation to complete.

1.  Once the installation completes, copy download the `kubeconfig` file and copy it to your host running the assisted service UI or a system that has the `oc` binary installed.

1.  Export the kubeconfig

        [$USER@assisted_installer ~]# export KUBECONFIG=/path/to/kubeconfig

1.  Verify everything is running as expected with your install

        [$USER@assisted_installer ~]# oc get nodes
        [$USER@assisted_installer ~]# oc get co
        [$USER@assisted_installer ~]# oc get pods --all-namespaces | grep -iv running | grep -iv complete

> NOTE: Currently there is an issue with the metal3 pod. The Assisted Installer team is aware of this.

## Troubleshooting

Also see the [troubleshooting section](https://docs.google.com/document/d/1WDc5LQjNnqpznM9YFTGb9Bg1kqPVckgGepS4KBxGSqw/edit#heading=h.ewz6a9wqulbj) in the **internal** [Assisted Deployment](https://docs.google.com/document/d/1WDc5LQjNnqpznM9YFTGb9Bg1kqPVckgGepS4KBxGSqw/edit?usp=sharing) document.

**Problem**

Minikube fails when deploying _assisted-service_ using the test infra.

**Solution**

Run:

```bash
make destroy
rm -f /usr/bin/docker-machine-driver-kvm2
make run
```

---

**Problem**

An exception in `discovery-infra/assisted_service_client.py` about a missing class or an invalid parameter.

**Solution**

1. Rebase _test-infra_ on top of _master_
2. Run `make image_build` to build a new test-infra image

> Do not use skipper commands in _test-infra_ :)

---

**Problem**

VMs fail to connect to Assisted Service.

**Solution**

1. Run `kubectl get pods -n <namespace>` and look for the _assisted-service_ pod name. For example:

```bash
[$USER@assisted_installer ~]# kubectl get pods -n assisted-installer
```

2. Run `kubectl logs <pod-name> -n <namespace>` and check the log for errors.

3. If you do not see any errors in the Assisted Service logs, ssh to the VM:

   - Get the VM IP addresses using `virsh net-dhcp-leases test-infra-net`.

   - `cd test-infra` and `chmod 600 ssh_key/key` (default SSH key)

   - `ssh -i ssh_key/key core@vm-ip` or try `ssh -i ssh_key/key systemuser@vm-ip` if it did not work

   - Agent logs are located under `/var/log/agent.log`

---

**Problem**

There are issues installing Assisted Service.

**Solution**

1. Run `kubectl get pods -n <namespace>` and look for the _assisted-service_ pod name. For example:

```bash
[$USER@assisted_installer ~]# kubectl get pods -n assisted-installer
```

2. Run `kubectl logs <pod-name> -n <namespace>` and the log for errors.

3. SSH to the VMs as described above, run `sudo su` and check podman logs of the assisted installer container for errors.

---

**Problem**

The test infra fails with any of the following errors:

- `Error: missing provider "libvirt"`

- `make image build failed - DD failed: stat /var/lib/docker/tmp/docker-builder287959213/build/assisted-service-client: no such file or directory`

- `warning: unable to access '/root/.gitconfig': Is a directory fatal: unknown error occurred while reading the configuration files`

**Solution**

Do not run test-infra from `/root`. Instead, move it to `/home/test/` and then run `make create_full_environment`.

---

**Problem**

You get an error with the message `Error: Error defining libvirt network: virError(Code=9, Domain=19, Message='operation failed: network 'test-infra-net' already exists`.

**Solution**

You probably already have a running cluster. Run `make destroy` do deleted the existing cluster. If it does not solve the issue, run `make delete_all_virsh_resources`.

---

**Problem**

You get `Error: Error creating libvirt domain: virError(Code=38, Domain=18, Message='Cannot access storage file '/home/test/test-infra/storage_pool/test-infra-cluster/test-infra-cluster-master-0' (as uid:107, gid:107): Permission denied')`.

**Solution**

Run `make create_full_environment`.

<hr>
<b id="f1">1</b> It can also be a VM running CentOS8 or RHEL8 and able to do `nested` virtualization as it will run minikube inside. VM should have NICs for connecting to the hosts being installed over bridges at the physical host. [↩](#a1)
