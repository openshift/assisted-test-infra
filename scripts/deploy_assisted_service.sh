#!/usr/bin/env bash
set -euo pipefail
source scripts/utils.sh

set -o xtrace

export SERVICE_NAME=assisted-service

case ${DEPLOY_TARGET} in
    kind)
        export SERVICE_URL=${SERVICE_URL:-$(get_main_ip)}
        export SERVICE_PORT=8090
        export IMAGE_SERVICE_PORT=8080
        export EXTERNAL_PORT=false
        ;;
    *)
        export SERVICE_URL=${SERVICE_URL:-$(get_main_ip)}
        export SERVICE_PORT=$(( 6000 + $NAMESPACE_INDEX ))
        export IMAGE_SERVICE_PORT=$(( 6016 + $NAMESPACE_INDEX ))
        ;;
esac

export AUTH_TYPE=${AUTH_TYPE:-none}
export NAMESPACE=${NAMESPACE:-assisted-installer}
export IMAGE_SERVICE_BASE_URL=${SERVICE_BASE_URL:-"http://${SERVICE_URL}:${IMAGE_SERVICE_PORT}"}
export SERVICE_INTERNAL_PORT=8090
export IMAGE_SERVICE_INTERNAL_PORT=8080
export SERVICE_BASE_URL=${SERVICE_BASE_URL:-"http://${SERVICE_URL}:${SERVICE_PORT}"}
export EXTERNAL_PORT=${EXTERNAL_PORT:-true}
export OCP_SERVICE_PORT=$(( 7000 + $NAMESPACE_INDEX ))
export OPENSHIFT_INSTALL_RELEASE_IMAGE=${OPENSHIFT_INSTALL_RELEASE_IMAGE:-}
export OPENSHIFT_VERSION=${OPENSHIFT_VERSION:-}
export OPENSHIFT_VERSIONS=${OPENSHIFT_VERSIONS:-}
export ENABLE_KUBE_API=${ENABLE_KUBE_API:-false}
export ENABLE_KUBE_API_CMD="ENABLE_KUBE_API=${ENABLE_KUBE_API}"
export DEBUG_SERVICE_NAME=assisted-service-debug
export IMAGE_SERVICE_NAME=assisted-image-service
export DEBUG_SERVICE_PORT=${DEBUG_SERVICE_PORT:-40000}
export REGISTRY_SERVICE_NAME=registry
export REGISTRY_SERVICE_NAMESPACE=kube-system
export REGISTRY_SERVICE_PORT=80
export REGISTRY_SERVICE_HOST_PORT=5000
export ENABLE_HOST_RECLAIM=${RECLAIM_HOSTS:-false}
export OPENSHIFT_CI=${OPENSHIFT_CI:-false}
export ENABLE_SKIP_MCO_REBOOT=${ENABLE_SKIP_MCO_REBOOT:-true}
export ENABLE_SOFT_TIMEOUTS=${ENABLE_SOFT_TIMEOUTS:-false}
export IMAGES_FLAVOR=${IMAGES_FLAVOR:-}
export PLATFORM=${PLATFORM:-}
export RELEASE_IMAGES=${RELEASE_IMAGES:-}
export OS_IMAGES=${OS_IMAGES:-}
export LOAD_BALANCER_TYPE=${LOAD_BALANCER_TYPE:-"cluster-managed"}
export NVIDIA_REQUIRE_GPU=${NVIDIA_REQUIRE_GPU:-true}
export AMD_REQUIRE_GPU=${AMD_REQUIRE_GPU:-true}
export ASSISTED_SERVICE_DATA_BASE_PATH="./assisted-service/data"
export RELEASE_IMAGES_PATH="${ASSISTED_SERVICE_DATA_BASE_PATH}/default_release_images.json"
export OS_IMAGES_PATH="${ASSISTED_SERVICE_DATA_BASE_PATH}/default_os_images.json"


if [ -n "${IMAGES_FLAVOR}" ]; then
    RELEASE_IMAGES_PATH="${ASSISTED_SERVICE_DATA_BASE_PATH}/default_${IMAGES_FLAVOR}_release_images.json"
    OS_IMAGES_PATH="${ASSISTED_SERVICE_DATA_BASE_PATH}/default_${IMAGES_FLAVOR}_os_images.json"
fi

if [[ "${ENABLE_KUBE_API}" == "true" || "${DEPLOY_TARGET}" == "operator" ]]; then
    # Only OS_IMAGES list is required in kube-api flow (assisted-service is using defaults if missing)
    if [ -z "${OPENSHIFT_VERSIONS:-}" ]; then
        export OPENSHIFT_VERSIONS='{}'
    fi
    if [ -z "${RELEASE_IMAGES:-}" ]; then
        export RELEASE_IMAGES='[]'
    fi
    # The kube-api flow sets all infra env image types to the ISO image type configured
    # when the service is deployed
    export ISO_IMAGE_TYPE=${ISO_IMAGE_TYPE:-minimal-iso}
fi

mkdir -p build

if [ "${RELEASE_IMAGES}" = "" ] && { [ "${OPENSHIFT_INSTALL_RELEASE_IMAGE}" != "" ] || [ "${OPENSHIFT_VERSION}" != "" ]; }; then
    RELEASE_IMAGES=$(skipper run ./scripts/override_images/override_release_images.py)
    export RELEASE_IMAGES

    if [ "${DEPLOY_TARGET}" == "onprem" ]; then
        (cd assisted-service; skipper make generate-configuration)
    fi
fi

if [ "${OS_IMAGES}" = "" ] && [ "${ENABLE_KUBE_API}" != "true" ] && [ "${DEPLOY_TARGET}" != "operator" ] && { [ "${OPENSHIFT_INSTALL_RELEASE_IMAGE}" != "" ] || [ "${OPENSHIFT_VERSION}" != "" ]; }; then
    OS_IMAGES=$(skipper run ./scripts/override_images/override_os_images.py)
    export OS_IMAGES
fi

# assisted-service has a mechanism for filtering images which filters out multi-arch images.
# This way we disable it as we already filtered here
unset OPENSHIFT_VERSION

if [ "${DEPLOY_TARGET}" == "onprem" ]; then
    # Override assisted-service and assisted-image-service
    if [ -n "${SERVICE:-}" ]; then
        sed -i "s|quay.io/edge-infrastructure/assisted-service:latest|${SERVICE}|g" assisted-service/deploy/podman/pod.yml
    fi
    if [ -n "${IMAGE_SERVICE:-}" ]; then
        sed -i "s|quay.io/edge-infrastructure/assisted-image-service:latest|${IMAGE_SERVICE}|g" assisted-service/deploy/podman/pod.yml
    fi

    # Override ConfigMap
    if [ -n "${INSTALLER_IMAGE:-}" ]; then
        echo "  INSTALLER_IMAGE: ${INSTALLER_IMAGE}" >> assisted-service/deploy/podman/configmap.yml
    fi
    if [ -n "${CONTROLLER_IMAGE:-}" ]; then
        echo "  CONTROLLER_IMAGE: ${CONTROLLER_IMAGE}" >> assisted-service/deploy/podman/configmap.yml
    fi
    if [ -n "${AGENT_DOCKER_IMAGE:-}" ]; then
        echo "  AGENT_DOCKER_IMAGE: ${AGENT_DOCKER_IMAGE}" >> assisted-service/deploy/podman/configmap.yml
    fi
    if [ -n "${PUBLIC_CONTAINER_REGISTRIES:-}" ]; then
        sed -i "s|PUBLIC_CONTAINER_REGISTRIES:.*|PUBLIC_CONTAINER_REGISTRIES: ${PUBLIC_CONTAINER_REGISTRIES}|" assisted-service/deploy/podman/configmap.yml
    fi
    if [ -n "${ASSISTED_SERVICE_HOST:-}" ]; then
	sed -i "s|SERVICE_BASE_URL: http://127.0.0.1|SERVICE_BASE_URL: http://${ASSISTED_SERVICE_HOST}|" assisted-service/deploy/podman/configmap.yml
    fi

    validator_requirements=$(grep HW_VALIDATOR_REQUIREMENTS assisted-service/deploy/podman/configmap.yml | awk '{ print $2 }' | tr -d \')
    HW_VALIDATOR_REQUIREMENTS_LOW_DISK=$(echo $validator_requirements | jq '(.[].worker.disk_size_gb, .[].master.disk_size_gb, .[].sno.disk_size_gb) |= 20' | tr -d "\n\t ")
    sed -i "s|HW_VALIDATOR_REQUIREMENTS:.*|HW_VALIDATOR_REQUIREMENTS: '${HW_VALIDATOR_REQUIREMENTS_LOW_DISK}'|" assisted-service/deploy/podman/configmap.yml

    ROOT_DIR=$(realpath assisted-service/) make -C assisted-service/ deploy-onprem
elif [ "${DEPLOY_TARGET}" == "operator" ]; then
    # This nginx would listen to http on OCP_SERVICE_PORT and it would proxy_pass it to the actual route.
    export SERVICE_BASE_URL=http://${SERVICE_URL}:${OCP_SERVICE_PORT}
    add_firewalld_port ${OCP_SERVICE_PORT}

    # TODO: Find a way to get the route dest dynamically.
    # Currently it's not possible since it would be available only after the operator would be deployed
    # The deploy.sh script would wait for the operator to succeed - so we need to have the LB before that.
    ROUTE=dummy.route

    tee << EOF ${HOME}/.test-infra/etc/nginx/conf.d/http_localhost.conf
upstream upstream_${SERVICE_URL//./_} {
    server ${ROUTE}:443;
}

server {
    listen ${SERVICE_URL}:${OCP_SERVICE_PORT};

    location / {
        proxy_pass https://upstream_${SERVICE_URL//./_};
        proxy_set_header Host ${ROUTE};
    }
}
EOF

    export DISKS="${LSO_DISKS:-}"
    export ASSISTED_NAMESPACE=${NAMESPACE}
    export SERVICE_IMAGE=${SERVICE}

    ./assisted-service/deploy/operator/deploy.sh
    echo "Installation of Assisted Install operator passed successfully!"

    # Update the LB configuration to point to the service route endpoint
    # Nginx is being updated every 60s
    # TODO: Restart nginx
    PATCH_ROUTE=$(kubectl get routes ${SERVICE_NAME} -n assisted-installer --no-headers | awk '{print $2}')
    sed -i "s/${ROUTE}/${PATCH_ROUTE}/g" "${HOME}/.test-infra/etc/nginx/conf.d/http_localhost.conf"
    sleep 60
else
    print_log "Updating assisted_service params"

    if [[ "${PLATFORM}" == "none"  || "${PLATFORM}" == "external" || "${LOAD_BALANCER_TYPE}" == "user-managed" ]]; then
        # on RHEl9 we need to open ports in a new policy
        # between libvirt and HOST
        print_log "Opening additional ports for none/external platform or user-managed load balancer"
        firewall-cmd --policy=libvirt-to-host --add-port={22623/tcp,22624/tcp,6443/tcp}
        firewall-cmd --policy=libvirt-to-host --add-service={http,https}
        firewall-cmd --zone=libvirt-routed  --add-forward
    fi

    skipper run src/update_assisted_service_cm.py

    (
    cd assisted-service/ && \
    skipper --env-file ../skipper.env run "make deploy-all" \
        ${SKIPPER_PARAMS} \
        $ENABLE_KUBE_API_CMD \
        TARGET=$DEPLOY_TARGET \
        DEPLOY_TAG=${DEPLOY_TAG} \
        DEPLOY_MANIFEST_PATH=${DEPLOY_MANIFEST_PATH} \
        DEPLOY_MANIFEST_TAG=${DEPLOY_MANIFEST_TAG} \
        NAMESPACE=${NAMESPACE} \
        AUTH_TYPE=${AUTH_TYPE} \
        ${DEBUG_DEPLOY_AI_PARAMS:-} \
        IP=${SERVICE_URL} \
        NVIDIA_REQUIRE_GPU=${NVIDIA_REQUIRE_GPU} \
        AMD_REQUIRE_GPU=${AMD_REQUIRE_GPU} \
    )

    add_firewalld_port $SERVICE_PORT

    if [ "${DEPLOY_TARGET}" == "minikube" ]; then
        print_log "Starting port forwarding for deployment/${SERVICE_NAME} on port $SERVICE_PORT"
        wait_for_url_and_run ${SERVICE_BASE_URL} "spawn_port_forwarding_command $SERVICE_NAME $SERVICE_PORT $NAMESPACE $NAMESPACE_INDEX $KUBECONFIG minikube undeclared $SERVICE_INTERNAL_PORT"
    fi

    if [[ "${DEBUG_SERVICE}" == "true" || "${USE_LOCAL_SERVICE}" == "true" ]]; then
        (cd assisted-service/ && make patch-service ROOT_DIR=$ROOT_DIR/assisted-service TARGET=$DEPLOY_TARGET)
    fi

    if [ "${DEBUG_SERVICE}" == "true" ]; then
        add_firewalld_port ${DEBUG_SERVICE_PORT}

        if [ "${DEPLOY_TARGET}" == "minikube" ]; then
            print_log "Starting port forwarding for deployment/${SERVICE_NAME} on debug port $DEBUG_SERVICE_PORT"
            spawn_port_forwarding_command $SERVICE_NAME $DEBUG_SERVICE_PORT $NAMESPACE $NAMESPACE_INDEX $KUBECONFIG minikube undeclaredip $DEBUG_SERVICE_PORT $DEBUG_SERVICE_NAME
        fi
    fi

    add_firewalld_port ${IMAGE_SERVICE_PORT}

    if [ "${DEPLOY_TARGET}" == "minikube" ]; then
        print_log "Starting port forwarding for deployment/${IMAGE_SERVICE_NAME} on debug port $IMAGE_SERVICE_PORT"
        spawn_port_forwarding_command $IMAGE_SERVICE_NAME $IMAGE_SERVICE_PORT $NAMESPACE $NAMESPACE_INDEX $KUBECONFIG minikube undeclaredip $IMAGE_SERVICE_INTERNAL_PORT $IMAGE_SERVICE_NAME
    fi

    print_log "${SERVICE_NAME} can be reached at ${SERVICE_BASE_URL} "
    print_log "Done"
fi
