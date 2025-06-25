# Guide: Testing Ofcir Heterogeneous Infrastructure Playbooks

This guide details the process for setting up a local Ofcir instance on a Minikube cluster. It then shows how to configure it with heterogeneous AWS instance pools and test the entire setup before running the Ansible playbooks for infrastructure creation and deletion.

### 1. Prerequisites

Before you begin, ensure you have the following installed and configured:

* `git`
* `make`
* `podman` (or another container driver for Minikube)
* `minikube`
* `kubectl` (or `oc`)
* `ansible`
* AWS credentials (`accessKey` and `secretAccessKey`) with permissions to manage EC2 instances.

### 2. Setup Ofcir on a Local k8s Cluster

These steps will create a local Kubernetes cluster, build the Ofcir container image, and deploy the service.

1.  **Clone the Ofcir project:**
    ```bash
    git clone https://github.com/openshift-eng/ofcir.git
    cd ofcir
    ```

2.  **Start Minikube and Deploy Ofcir:**
    This command starts a rootless Minikube cluster, builds the Ofcir image into it, generates the necessary Kubernetes manifests, and applies them.
    ```bash
    # Start a rootless cluster using the podman driver
    minikube start --driver=podman --container-runtime=containerd --rootless=true

    # Build the ofcir image directly into the minikube instance
    minikube image build -t ofcir.io/ofcir:latest .

    # Generate and apply the deployment manifests
    make generate-deploy-manifests
    kubectl apply -f ofcir-manifests/
    ```

3.  **Expose the Ofcir Service:**
    Use `port-forward` to make the Ofcir service accessible on your local machine. We select the pod using its application label for reliability.
    ```bash
    # Wait for the pod to be in the 'Running' state
    echo "Waiting for Ofcir pod to be ready..."
    kubectl wait --for=condition=ready pod -n ofcir-system --timeout=300s

    # Get the pod name and start port-forwarding in the background
    OFCIR_POD_NAME=$(kubectl get pods -n ofcir-system -o jsonpath='{.items[0].metadata.name}')
    kubectl -n ofcir-system port-forward "${OFCIR_POD_NAME}" 8443:8443 &
    PORT_FORWARD_PID=$!
    echo "Port-forwarding started with PID ${PORT_FORWARD_PID}. Run 'kill ${PORT_FORWARD_PID}' to stop it."
    ```
    *You can test basic connectivity now: `nc -zv 127.0.0.1 8443`*

### 3. Configure Resource Pools and Secrets

Now, we will define two different CI (Continuous Integration) resource pools and the secrets required to provision machines in them.

1.  **Create CIPool Resources:**
    These custom resources define the types of machines Ofcir can provision.
    ```bash
    # Pool for ARM64 instances
    kubectl apply -f - <<-"EOF"
    apiVersion: ofcir.openshift/v1
    kind: CIPool
    metadata:
      name: cipool-assisted-aws-arm64-fallback
      namespace: ofcir-system
    spec:
      priority: -1
      provider: aws
      size: 5
      state: available
      timeout: 5h30m0s
      type: assisted_arm64_el9
    EOF

    # Pool for x86 (medium) instances
    kubectl apply -f - <<-"EOF"
    apiVersion: ofcir.openshift/v1
    kind: CIPool
    metadata:
      name: cipool-assisted-aws-medium-fallback
      namespace: ofcir-system
    spec:
      priority: -1
      provider: aws
      size: 5
      state: available
      timeout: 5h30m0s
      type: assisted_medium_el9
    EOF
    ```

2.  **Create Provider Secrets:**
    These secrets contain the AWS credentials and machine specifications. Using `kubectl create secret` is safer than applying a YAML file with placeholder credentials.

    **Note:** The `userData` field contains a base64-encoded cloud-init script. The decoded script is shown for clarity.
    ```yaml
    # Decoded userData:
    # #cloud-config
    # disable_root: false           # keep root enabled at boot
    #
    # runcmd:
    #  - |
    #    # Remove any options (command=, no-*, etc.) that precede the key type
    #    sed -Ei 's/.*(ssh-(rsa|ed25519))/\1/' /root/.ssh/authorized_keys
    ```

    **Run these commands, replacing placeholders with your actual AWS credentials:**
    ```bash
    # Secret for the ARM64 pool
    kubectl create secret generic cipool-assisted-aws-arm64-fallback-secret \
      -n ofcir-system \
      --from-literal=config='{"accessKey":"<YOUR_AWS_KEY>","secretAccessKey":"<YOUR_AWS_SECRET_KEY>","userData":"I2Nsb3VkLWNvbmZpZwpkaXNhYmxlX3Jvb3Q6IGZhbHNlICAgICAgICAgICAgICMga2VlcCByb290IGVuYWJsZWQgYXQgYm9vdAoKcnVuY21kOgogIC0gfAogICAgIyBSZW1vdmUgYW55IG9wdGlvbnMgKGNvbW1hbmQ9LCBuby0qLCBldGMuKSB0aGF0IHByZWNlZGUgdGhlIGtleSB0eXBlCiAgICBzZWQgLUVpICdzL14uKihzc2gtKHJzYXxlZDI1NTE5KSkvXDEvJyAvcm9vdC8uc3NoL2F1dGhvcml6ZWRfa2V5cwo=","machineSpec":{"regions":[{"name":"us-east-1","keyPairName":"assisted-installer-ci","securityGroupID":"sg-0e734795b128e792a","subnetID":"subnet-038f4d7a5c1df449d","instances":[{"type":"c6g.metal","amiID":"ami-0091bb44bfaef1c17"}]}],"device":{"deviceName":"/dev/sda1","deviceSize":1024,"deviceType":"gp2"}}}'

    # Secret for the x86 medium pool
    kubectl create secret generic cipool-assisted-aws-medium-fallback-secret \
      -n ofcir-system \
      --from-literal=config='{"accessKey":"<YOUR_AWS_KEY>","secretAccessKey":"<YOUR_AWS_SECRET_KEY>","userData":"I2Nsb3VkLWNvbmZpZwpkaXNhYmxlX3Jvb3Q6IGZhbHNlICAgICAgICAgICAgICMga2VlcCByb290IGVuYWJsZWQgYXQgYm9vdAoKcnVuY21kOgogIC0gfAogICAgIyBSZW1vdmUgYW55IG9wdGlvbnMgKGNvbW1hbmQ9LCBuby0qLCBldGMuKSB0aGF0IHByZWNlZGUgdGhlIGtleSB0eXBlCiAgICBzZWQgLUVpICdzL14uKihzc2gtKHJzYXxlZDI1NTE5KSkvXDEvJyAvcm9vdC8uc3NoL2F1dGhvcml6ZWRfa2V5cwo=","machineSpec":{"regions":[{"name":"us-east-1","keyPairName":"assisted-installer-ci","securityGroupID":"sg-0e734795b128e792a","subnetID":"subnet-038f4d7a5c1df449d","instances":[{"type":"c5n.metal","amiID":"ami-0a73e96a849c232cc"}]}],"device":{"deviceName":"/dev/sda1","deviceSize":1024,"deviceType":"gp2"}}}'
    ```

3.  **Authorize the New Pools:**
    Patch the `ofcir-tokens` secret. This secret maps an authentication token to a list of provider secrets that the token is allowed to use. Here, we allow the default `"token"` to access both of our new pools.
    ```bash
    kubectl patch secret ofcir-tokens -n ofcir-system -p '{"stringData": {"token": "cipool-assisted-aws-medium-fallback-secret,cipool-assisted-aws-arm64-fallback-secret"}}'
    ```

### 4. Test the Ofcir API

You can now request a resource from one of the pools to verify the setup works.

1.  **Request a Resource:**
    ```bash
    # Request an ARM64 machine
    curl --insecure -H "X-OFCIRTOKEN: token" -X POST "https://127.0.0.1:8443/v1/ofcir?type=assisted_arm64_el9"
    ```

    A successful response will look like this. **Take note of the `name` field (e.g., `cir-0011`).**
    ```json
    {
        "name": "cir-0011",
        "pool": "cipool-assisted-aws-arm64-fallback",
        "provider": "aws",
        "providerInfo": "",
        "type": "assisted_arm64_el9"
    }
    ```

2.  **Release the Resource:**
    Use the `name` from the previous step to release the resource back to the pool.
    ```bash
    # Replace cir-0011 with the name you received
    CIR_NAME="cir-0011"
    curl --insecure -X DELETE -H "X-OFCIRTOKEN: token" "https://127.0.0.1:8443/v1/ofcir/${CIR_NAME}"
    ```
    A successful deletion will return the name of the resource you released.

### 5. Run the Ansible Playbooks

Now that Ofcir is running and configured, you can run the test playbooks.

**Note:** The following commands assume you have the `assisted-test-infra` repository checked out and are running them from the `.../assisted-test-infra/ansible_files` directory.

**Create Infrastructure:**
```bash
ansible-playbook -e "@vars/standalone_ofcir_hetrogeneous_infra_sample.yml" ofcir_hetrogeneous_create_infra_playbook.yml
```

**Destroy Infrastructure:**
```bash
ansible-playbook -e "@vars/standalone_ofcir_hetrogeneous_infra_sample.yml" ofcir_hetrogeneous_destroy_infra_playbook.yml
```

### 6. Cleanup
```bash
# Stop the port-forwarding process
kill ${PORT_FORWARD_PID}

# Delete the minikube cluster
minikube delete
```
