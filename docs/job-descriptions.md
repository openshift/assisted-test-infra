### e2e-metal-assisted
Installs a multi-node OpenShift cluster on Equinix Metal
(bare‑metal‑as‑a‑service) using the Assisted Installer REST API. CI leases
bare‑metal hosts, generates a discovery ISO and ignition, and boots each node
so it auto‑registers with assisted‑service. It performs a day‑1 install
(initial cluster creation) until the cluster reports Installed. Boot medium is
the Assisted discovery ISO (mounted or virtual‑media). After installation, the
job runs a short openshift‑tests conformance smoke to verify core APIs,
authentication, and operator health. This job validates the end‑to‑end Assisted
bare‑metal installation path on real hardware.

### e2e-metal-assisted-cnv
Installs a multi‑node OpenShift cluster on Equinix Metal and enables OpenShift
Virtualization (CNV) during installation via Operator Lifecycle Manager (OLM).
Assisted injects the CNV subscription/manifests before first boot so the
operator deploys as the cluster comes up. The cluster must converge with
virtualization components (KubeVirt, hostpath provisioner) healthy. After
installation, a short openshift‑tests smoke ensures both CNV and core cluster
operators remain stable. This validates Assisted day‑1 optional‑operator
enablement for CNV on bare metal.

### e2e-metal-assisted-day2
Installs a multi‑node OpenShift cluster on Equinix Metal and then exercises
day‑2 scale‑out (post‑install operations). Additional worker hosts boot a
discovery ISO produced by an InfraEnv (an Assisted resource that generates
per‑cluster discovery images), are approved in assisted‑service, installed, and
must join the cluster as Ready nodes. The job validates day‑2 agent image
rollouts, join validations, and reconciliation beyond initial (day‑1) install.
It concludes with a basic health smoke over the enlarged cluster to confirm
steady state.

### e2e-metal-assisted-external
Installs a multi‑node OpenShift cluster on Equinix Metal with
platform=external, where virtual IPs (VIPs), DNS, and load balancer are
user‑managed. Assisted‑service must not program networking or infrastructure
and should succeed with externally provided endpoints. The job confirms control
plane stability, correct VIP handling, and that cluster install completes
without Assisted‑managed load balancing or DNS.

### e2e-metal-assisted-ipv6
Installs a multi‑node OpenShift cluster on Equinix Metal in IPv6‑only mode
(IPv6 enabled, IPv4 disabled). Assisted must generate ignition and network
configuration without IPv4 assumptions, and each node must discover, install,
and converge using only IPv6. After installation, the job runs a short
openshift‑tests conformance smoke to validate API reachability and operator
stability over IPv6 networking.

### e2e-metal-assisted-lvm
Installs a compact OpenShift cluster on Equinix Metal with three control‑plane
nodes and no workers, enabling the Logical Volume Manager (LVM) Storage
operator via OLM during install. Masters receive multiple disks so LVM can
create storage classes and reconcile successfully. The job validates Assisted’s
operator manifest injection, disk hinting, and storage readiness, and ensures
the cluster remains healthy after LVM becomes available.

### e2e-metal-assisted-odf
Installs a six‑node OpenShift cluster on Equinix Metal (three control‑plane and
three worker nodes) with OpenShift Data Foundation (ODF) enabled during
installation via OLM. The job uses larger instances with multiple disks to
satisfy ODF requirements, validates that Assisted injects correct ODF
manifests, and ensures data‑plane operators settle post‑install without
degradation.

### e2e-metal-assisted-single-node
Performs a bootstrap‑in‑place (BIP) installation of a Single‑Node OpenShift
(SNO) cluster on Equinix Metal. The job provisions one node (no workers),
generates a BIP ISO that includes bootstrap content, and installs the control
plane directly on that node (no separate bootstrap host). It validates that
Assisted SNO installs complete and the node reaches Installed and Ready.

### e2e-oci-assisted
Installs a multi‑node OpenShift cluster on Oracle Cloud Infrastructure (OCI)
using Assisted. A CI setup step uses Ansible to create base OCI networking and
compute. The job then boots the Assisted discovery ISO on those instances and
performs the day‑1 install until the cluster is Installed. A short
openshift‑tests smoke verifies cluster health, validating Assisted’s
cloud‑based provisioning path on OCI.

### e2e-agent-4control-ipv4
Performs an agent‑based installation of OpenShift on Equinix Metal with four
control‑plane nodes (no workers required). In agent‑based installs, hosts boot
an “agent” image and the cluster is driven by Kubernetes custom resources
rather than the Assisted REST API. This job validates control‑plane scaling and
etcd quorum behavior with four masters on bare metal, and confirms the cluster
reaches Installed and remains healthy.

### e2e-agent-5control-ipv4
Performs an agent‑based installation on Equinix Metal with five control‑plane
nodes (no workers). This stresses control‑plane scalability beyond the common
three‑master topology. The job validates installation success, etcd quorum and
control‑plane stability with five masters, and confirms steady‑state cluster
health post‑install.

### e2e-agent-compact-ipv4
Performs an agent‑based “compact” install on Equinix Metal: three control‑plane
nodes (no workers) for day‑1, then adds two workers as a day‑2 operation. The
job enables FIPS mode and uses OVN‑Kubernetes for networking. It validates both
initial control‑plane convergence and the day‑2 worker join path in the
agent‑based method.

### e2e-agent-ha-dualstack
Performs an agent‑based installation of a highly available OpenShift cluster on
Equinix Metal with dual‑stack networking enabled (both IPv4 and IPv6). It
exercises DHCP and VIP configuration under dual addressing and validates that
control plane and services remain reachable over both IP families after
installation.

### e2e-agent-sno-ipv6
Performs an agent‑based installation of Single‑Node OpenShift (SNO) in
IPv6‑only mode on Equinix Metal. Each node’s ignition and host CSR flow must
succeed without IPv4. The job validates that the control plane becomes Ready
and remains stable using only IPv6 networking.

### e2e-ai-operator-ztp
Validates Zero‑Touch Provisioning (ZTP) using the Assisted Service Operator.
The job first creates a “hub” cluster, deploys the operator, and then defines a
managed “spoke” cluster using Kubernetes custom resources: InfraEnv (generates
discovery images), Agent (represents hosts), and AgentClusterInstall (drives
install). It waits for the spoke to reach Installed and then verifies health
using the spoke’s kubeconfig. This proves operator‑managed, CR‑driven
bare‑metal installation.

### e2e-metal-assisted-ha-kube-api-ipv4
Installs a highly available OpenShift cluster on Equinix Metal using the
Kubernetes API‑driven method (operator + CRs) over IPv4. Instead of using the
Assisted REST API directly, the job deploys the Assisted Service Operator on a
hub cluster, creates InfraEnv/Agent/AgentClusterInstall resources, and lets the
operator perform installation. It then runs a parallel kube‑API test suite to
confirm the CR‑driven flow produces a healthy cluster.

### e2e-metal-assisted-ha-kube-api-ipv6
Installs a highly available OpenShift cluster on Equinix Metal using the
Kubernetes API‑driven method (operator + CRs) in IPv6‑only mode (IPv6 enabled,
IPv4 disabled). Hosts boot a small “minimal ISO” that pulls installation
content from assisted‑service at runtime. After installation, a parallel
kube‑API test suite validates the cluster and operators over IPv6 networking.

### e2e-vsphere-assisted
Installs an OpenShift control plane on VMware vSphere using the Assisted
Installer REST API (typically with zero workers). The job boots vSphere VMs
with the Assisted discovery ISO, discovers agents, and performs the day‑1
install until the control plane is Installed. A short openshift‑tests smoke
confirms API and operator health, validating vSphere provider support for
Assisted installs.

### e2e-ai-operator-disconnected-capi
Validates operator‑managed installation using Cluster API (CAPI) and HyperShift
(hosted control planes) in a disconnected IPv6 environment. The job installs a
hub cluster, deploys the Assisted Operator, installs HyperShift and the
cluster‑api‑provider‑agent, and then provisions a spoke using CAPI resources.
With DISCONNECTED=true and IPv6‑only networking, it proves the flow works with
mirrored registries and no external pulls.

### e2e-ai-operator-ztp-3masters
Creates a ZTP‑managed spoke cluster with three control‑plane agents (high
availability). The job confirms that the operator’s CR generation,
reconciliation, and wait logic scale to an HA control plane, and that the
resulting cluster reaches Installed and remains healthy after installation.

### e2e-ai-operator-ztp-capi
Performs Zero‑Touch Provisioning using Cluster API instead of
AgentClusterInstall resources. The job deploys HyperShift and the
cluster‑api‑provider‑agent on the hub and creates the spoke via CAPI objects.
It validates operator + HyperShift + CAPI interoperability for Assisted‑backed
bare‑metal installations.

### e2e-ai-operator-ztp-disconnected
Runs the ZTP operator flow in a disconnected IPv6 environment. The job relies
on mirrored registries (DISCONNECTED=true) and IPv6‑only networking (IP stack
v6). It validates that the operator can reconcile all resources and complete
installation without external image pulls.

### e2e-ai-operator-ztp-node-labels
Installs a ZTP‑managed spoke cluster and applies manifests that create
MachineConfigPools (MCPs) and label specific nodes (for example, labeling nodes
as infra). The job validates that the operator‑managed cluster accepts the
labels, MCPs reconcile, and workloads/daemons for the new pool converge without
disruption.

### e2e-metal-assisted-upgrade-agent
Validates the Assisted agent upgrade mechanism before cluster installation. The
job edits the assisted‑service configuration to use a different agent container
image, prepares the cluster for installation, then switches back to the
original image and waits until all hosts report the updated agent image. This
proves the service can roll agent versions safely prior to install.

### e2e-aws-ovn
Runs OpenShift end‑to‑end tests on Amazon Web Services using the OVN‑Kubernetes
network plugin. This job is not part of the Assisted flow but serves as a
generic reference for component and networking validation with the standard
e2e‑aws‑ovn suite.

### e2e-metal-assisted-day2-arm-workers
Installs an x86_64 OpenShift cluster on Equinix Metal and adds day‑2 ARM64
worker nodes. The job uses multi‑architecture agent/controller/installer images
so ARM64 hosts can discover and join via InfraEnv. It validates heterogeneous
CPU architecture handling during discovery, installation, and post‑install
joins.

### e2e-metal-assisted-deploy-nodes
Performs provisioning only on Equinix Metal: the job boots hosts with the
Assisted discovery ISO so they register and report inventory to
assisted‑service, but it does not proceed with cluster installation. This
validates discovery, hardware inventory collection, and environment preparation
without the time cost of a full install.

### e2e-metal-assisted-bond
Installs an OpenShift cluster on Equinix Metal with NIC bonding enabled on
hosts (for example, LACP or active‑backup). The job validates that Assisted can
provision with bonded interfaces, VIPs resolve correctly over the bonds, and
the cluster reaches Installed and remains healthy.

### e2e-metal-assisted-day2-sno
Installs a Single‑Node OpenShift (SNO) cluster on Equinix Metal using
bootstrap‑in‑place, then adds a worker node as a day‑2 operation. The job
validates that SNO deployments can expand, the worker joins and becomes Ready,
and the cluster remains healthy after expansion.

### e2e-metal-assisted-ipv4v6
Installs an OpenShift cluster on Equinix Metal with dual‑stack networking (both
IPv4 and IPv6). Assisted must generate correct ignition and network
configuration for both families, and the cluster must converge with services
reachable over IPv4 and IPv6. A short openshift‑tests smoke confirms
post‑install health.

### e2e-metal-assisted-ipxe
Validates iPXE network boot on Equinix Metal. CI serves an iPXE script that
downloads the Assisted live image, and hosts boot from the network instead of
local ISO media. The job ensures hosts discover correctly via iPXE and that the
subsequent Assisted installation completes and yields a healthy cluster.

### e2e-metal-assisted-kube-api-late-binding-sno
Validates late‑binding semantics for Single‑Node OpenShift using the Kubernetes
API‑driven method. In late binding, agents register to the hub but are not
assigned to a cluster until the final step. The job binds the agent and
installs via operator custom resources, then runs kube‑API tests to confirm the
CR‑driven install succeeded on SNO.

### e2e-metal-assisted-kube-api-late-unbinding-sno
Begins a Kubernetes API‑driven Single‑Node OpenShift installation, sets
HOLD_INSTALLATION=true, unbinds the agent prior to completion, and verifies
cleanup. The job validates that operator cleanup and assisted‑service state
transitions handle aborts gracefully for SNO clusters.

### e2e-metal-assisted-kube-api-reclaim
After completing a Kubernetes API‑driven multi‑node install on Equinix Metal,
the job unbinds the agents (RECLAIM_HOSTS=true) and expects them to return to
the Discovering state so they can be reused. This validates host reclaim logic
and clean lifecycle transitions for future installs.

### e2e-metal-assisted-kube-api-reclaim-sno
Single‑Node OpenShift variant of reclaim. The job performs a Kubernetes
API‑driven SNO install on Equinix Metal, unbinds the node after completion, and
verifies the host re‑enters the pool as Discovering. This confirms reclaim
works with bootstrap‑in‑place semantics.

### e2e-metal-assisted-kube-api-umlb
Installs a multi‑node OpenShift cluster on Equinix Metal via the Kubernetes
API‑driven method using a user‑managed external load balancer
(LOAD_BALANCER_TYPE=user‑managed). The job confirms the operator waits
appropriately for external LB readiness, control plane endpoints are correctly
targeted, and installation succeeds without Assisted‑managed load balancing.

### e2e-metal-assisted-sno
Runs a lightweight Single‑Node OpenShift (SNO) sanity test on Equinix Metal
using Assisted. It provisions one node, performs a bootstrap‑in‑place install,
and validates that the node becomes Ready. This provides a fast health signal
for changes that might impact SNO installs.

### e2e-metal-assisted-none
Installs a multi‑node OpenShift cluster on Equinix Metal with PLATFORM=none to
validate provider‑agnostic paths. The job ensures no cloud‑specific assumptions
leak into ignition generation or network configuration and confirms that the
cluster installs successfully without platform integration.

### e2e-metal-assisted-onprem
Installs an OpenShift cluster using the on‑premises profile
(DEPLOY_TARGET=onprem). The job runs against a locally managed “hub”
environment instead of cloud‑leased hosts, validating on‑premises sizing
defaults, ignition tweaks, and the absence of cloud dependencies while still
completing day‑1 installation successfully.

### e2e-metal-assisted-openshift-ai
Installs a larger OpenShift cluster on Equinix Metal and enables the OpenShift
AI operator bundle during installation (including components like Pipelines,
Service Mesh, Node Feature Discovery, and ODF). The job sets flags so no
physical GPUs are required in CI. It validates that the AI stack operators
deploy cleanly post‑install and that the cluster remains healthy under the
added load.

### e2e-metal-assisted-osc
Installs a multi‑node OpenShift cluster on Equinix Metal and enables OpenShift
Sandboxed Containers (OSC, Kata Containers) via OLM during installation.
Assisted injects the OSC subscription/manifests so the operator deploys as the
cluster comes up. The job validates that OSC components reconcile and the
cluster remains healthy post‑install.

### e2e-metal-assisted-osc-sno
Performs a Single‑Node OpenShift (SNO) installation on Equinix Metal and
enables the OpenShift Sandboxed Containers (OSC) operator. The job validates
that OSC deploys correctly on a constrained, single‑node footprint and that the
node stabilizes with OSC components installed.

### e2e-metal-assisted-static-ip-suite
Installs an OpenShift cluster on Equinix Metal with static host networking
(STATIC_IPS=true). The job exercises networking tests for static addressing,
VIPs, and routing under Assisted day‑1 installation. It confirms that static
network configuration yields a functional, healthy cluster.

### e2e-metal-assisted-tang
Installs an OpenShift cluster on Equinix Metal with disk encryption configured
to use Tang (DISK_ENCRYPTION_MODE=tang). CI starts a Tang server (a network key
escrow service), publishes its thumbprint, and the cluster installs with LUKS
using Tang for decryption keys. The job validates remote‑key disk encryption
integration in Assisted.

### e2e-metal-assisted-tpmv2
Installs an OpenShift cluster on Equinix Metal with disk encryption configured
to use TPM 2.0 (DISK_ENCRYPTION_MODE=tpmv2). This validates platform Trusted
Platform Module integration for LUKS without relying on external key servers,
confirming install and unlock paths across reboots.

### e2e-metal-assisted-umlb
Installs an OpenShift cluster on Equinix Metal with a user‑managed external
load balancer (LOAD_BALANCER_TYPE=user‑managed). The job validates that
installation and control‑plane/router health do not depend on an
Assisted‑managed load balancer, and that external LB endpoints are correctly
used throughout installation and steady state.

### e2e-metal-assisted-virtualization
Installs a multi‑node OpenShift cluster on Equinix Metal and enables a broader
virtualization operator bundle during installation via OLM. The bundle
typically includes CNV (OpenShift Virtualization) plus related operators like
Migration Toolkit for Virtualization (MTV), NMState, Node Health Check, and
others. The job uses larger instances and multiple disks to meet requirements
and validates that these optional operators stabilize post‑install.

### e2e-metal-assisted-ai-amd
Installs a larger OpenShift cluster on Equinix Metal and enables AMD
GPU‑related operators (for example, AMD GPU Operator and Kernel Module
Management) along with the OpenShift AI bundle (including Pipelines,
Serverless, Service Mesh, and ODF). The job sets AMD_REQUIRE_GPU=false so CI
succeeds without physical GPUs. It validates that all operators deploy and the
cluster remains healthy under the added workload.

### e2e-metal-assisted-ai-nvidia
Installs a larger OpenShift cluster on Equinix Metal and enables the NVIDIA GPU
Operator alongside the OpenShift AI bundle (Pipelines, Serverless, Service
Mesh, ODF, and dependencies). The job sets NVIDIA_REQUIRE_GPU=false so physical
GPUs are not required in CI. It validates that the AI stack deploys and the
cluster remains healthy with the NVIDIA operator present.

### e2e-metal-assisted-kube-api-net-suite
Runs a networking‑focused Kubernetes API‑driven installation on Equinix Metal
using a Single‑Node OpenShift footprint, a minimal ISO (a small boot image that
pulls content from assisted‑service at runtime), and static IP addressing. It
executes kube‑API tests in parallel to validate that static networking and the
operator‑driven install method coexist and yield a healthy cluster.

### e2e-metal-assisted-ha-kube-api
Installs a highly available OpenShift cluster on Equinix Metal using the
Kubernetes API‑driven method (Assisted Operator with
InfraEnv/Agent/AgentClusterInstall custom resources). It then runs kube‑API
tests in parallel and a short openshift‑tests conformance smoke. This confirms
core APIs and operators are healthy when installation is managed entirely by
the operator and CRs (as opposed to the Assisted REST API).

### e2e-metal-assisted-4-control-planes
Installs an OpenShift cluster on Equinix Metal with four control‑plane nodes
(NUM_MASTERS=4) and at least one worker. The job validates Assisted scaling
beyond the common three‑master topology, ensuring etcd quorum and control‑plane
scheduling remain healthy during and after installation.

### e2e-metal-assisted-5-control-planes
Installs an OpenShift cluster on Equinix Metal with five control‑plane nodes
(NUM_MASTERS=5). This stresses control‑plane scalability beyond four masters.
The job confirms Assisted can install and that etcd, API server, and scheduler
remain stable at this scale.

### e2e-metal-assisted-4-masters-none
Installs an OpenShift cluster on Equinix Metal with four control‑plane nodes
(NUM_MASTERS=4) and PLATFORM=none (no platform/provider integration). The job
validates provider‑agnostic code paths under a larger control plane and ensures
VIP and networking logic work without platform helpers.

### e2e-metal-sno-live-iso
Bootstraps a Single‑Node OpenShift cluster using the Assisted “live ISO” path
and installs in place. This exercises bootstrap‑in‑place (BIP) flows that run
from a live environment and confirms the node reaches Installed and Ready. It
provides fast coverage of SNO image creation and the in‑place install process.

### e2e-metal-sno-with-worker-live-iso
Starts from a Single‑Node OpenShift cluster installed via bootstrap‑in‑place
and adds a worker using the live ISO to boot the additional node. The job
validates that SNO clusters can expand and that the worker joins and becomes
Ready after the addition.

### e2e-oci-assisted-bm-iscsi
Installs an OpenShift cluster on Oracle Cloud Infrastructure using large
bare‑metal shapes (for example, BM.Standard classes). The job validates the
Assisted OCI flow on hardware‑backed instances and exercises storage/boot
patterns expected on OCI bare metal, including scenarios relevant to
iSCSI‑capable hosts.

### e2e-vsphere-assisted-kube-api
Installs an OpenShift control plane on VMware vSphere using the Kubernetes
API‑driven method (Assisted Operator with custom resources) and a minimal ISO,
typically with zero workers. The job runs kube‑API tests in parallel to
validate that the CR‑driven install path works on vSphere and yields a healthy
cluster.

### e2e-vsphere-assisted-umlb
Installs an OpenShift cluster on VMware vSphere using the Assisted REST API
while relying on a user‑managed external load balancer
(LOAD_BALANCER_TYPE=user‑managed). This validates correct interaction between
vSphere networking and external LBs during installation and steady state.

### e2e-vsphere-assisted-umn
Installs an OpenShift cluster on VMware vSphere using the Assisted REST API
with user‑managed networking (USER_MANAGED_NETWORKING=true). This confirms
Assisted can install successfully without programming platform networking in
vSphere environments.

### e2e-metal-assisted-kube-api-late-binding-single-node
Validates late‑binding for Single‑Node OpenShift using the Kubernetes
API‑driven method. Agents register to the hub but remain unassigned until the
final bind step; installation then proceeds through operator custom resources.
The job runs kube‑API tests to verify the resulting SNO cluster is healthy.

### e2e-metal-assisted-kube-api-late-unbinding-single-node
Begins a Kubernetes API‑driven SNO install on Equinix Metal, sets
HOLD_INSTALLATION=true to pause, unbinds the agent, and verifies cleanup and
state transitions. The job ensures abort paths and unbind behavior are correct
for single‑node operator installs.

### e2e-metal-assisted-kube-api-reclaim-single-node
Performs a Kubernetes API‑driven SNO install, then unbinds the node and
confirms it returns to the Discovering state for reuse. This exercises reclaim
logic on a bootstrap‑in‑place SNO installation and proves host lifecycle can be
restarted cleanly.

### e2e-metal-assisted-kube-api-net-suite-4-19
Runs a Kubernetes API‑driven networking suite on Equinix Metal tailored to a
specific OpenShift release stream. Using a minimal ISO and static IP addresses,
the job executes kube‑API tests to validate networking behavior under stricter
assumptions while keeping the overall flow version‑agnostic in concept.

### cluster-profile-assisted
Runs periodically to check and clean up the Equinix Metal host pool used by
Assisted jobs. The job detects leaked or long‑lived machines and reclaims them
when they exceed a time threshold, keeping the pool healthy and capacity
available for consumer jobs.

### cluster-profile-sno
Runs periodically to verify capacity and health of the Equinix Metal pool
dedicated to Single‑Node OpenShift (SNO) jobs. It detects and reclaims leaked
SNO hosts so that single‑node jobs always have available capacity.

### cluster-profile-oci-assisted
Runs daily to clean up Oracle Cloud Infrastructure resources used by Assisted
OCI jobs. It tears down or repairs leaked base infrastructure so OCI capacity
remains available for CI and unnecessary costs are avoided.

### e2e-ai-operator-ztp-sno-day2-workers
Creates a ZTP‑managed Single‑Node OpenShift spoke and adds a worker as a day‑2
operation. Using InfraEnv and Agent custom resources, the job provisions the
new node and validates it reaches Ready, confirming that SNO clusters can
expand under operator management.

### e2e-ai-operator-ztp-sno-day2-workers-late-binding
Adds a worker to a ZTP‑managed Single‑Node OpenShift spoke using late‑binding
semantics (the new host is not bound until the final step). The job validates
that operator and custom‑resource flows handle late binding correctly when
adding capacity to SNO.

### e2e-ai-operator-ztp-sno-day2-workers-ignitionoverride
Adds a worker to a ZTP‑managed SNO spoke with a BareMetalHost ignition override
applied. The job validates per‑node ignition customization in operator‑managed
clusters and ensures the customized node still joins and becomes Ready.

### e2e-ai-operator-ztp-sno-day2-masters
Expands a ZTP‑managed Single‑Node OpenShift spoke by adding a control‑plane
node as a day‑2 operation, transitioning from single‑node to multi‑node
topology. The job validates operator handling of control‑plane scale‑up and
confirms etcd/quorum health post‑expansion.

### e2e-ai-operator-ztp-compact-day2-masters
Adds a new control‑plane node to a ZTP‑managed compact spoke (three masters) as
a day‑2 operation. The job exercises operator handling of control‑plane
scale‑up and confirms etcd/quorum health after the new master joins.

### e2e-ai-operator-ztp-compact-day2-workers
Adds workers as a day‑2 operation to a ZTP‑managed compact spoke. The job
validates worker scale‑out via custom resources and confirms scheduling
capacity increases as expected after the new nodes become Ready.

### e2e-ai-operator-ztp-multiarch-3masters-ocp
Creates a ZTP‑managed spoke with three control‑plane nodes using
multi‑architecture OpenShift release images. The job ensures the operator can
reconcile and install when payloads are multi‑arch and validates steady‑state
cluster health post‑install.

### e2e-ai-operator-ztp-multiarch-sno-ocp
Performs a Single‑Node OpenShift ZTP flow using multi‑architecture OpenShift
release images. The job confirms InfraEnv/Agent flows and operator
reconciliation work correctly when the payload is multi‑arch.

### e2e-ai-operator-ztp-remove-node
Removes a worker from a ZTP‑managed spoke after installation. The job validates
day‑2 node removal, ensures the cluster stays healthy post‑removal, and
confirms associated custom resources and state are cleaned up appropriately.

### e2e-ai-operator-ztp-4masters
Creates a ZTP‑managed spoke with four control‑plane agents. The job confirms
that operator reconciliation scales to larger control planes and that
etcd/quorum and control‑plane services stabilize after installation.

### e2e-ai-operator-ztp-5masters
Creates a ZTP‑managed spoke with five control‑plane agents. This further
stresses control‑plane scaling under operator management and validates that
steady‑state cluster health is maintained after installation.
