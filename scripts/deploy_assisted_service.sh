#!/usr/bin/env bash
set -euo pipefail
source scripts/utils.sh

set -o xtrace

export SERVICE_NAME=assisted-service
export SERVICE_URL=$(get_main_ip)
export AUTH_TYPE=${AUTH_TYPE:-none}
export NAMESPACE=${NAMESPACE:-assisted-installer}
export SERVICE_PORT=$(( 6000 + $NAMESPACE_INDEX ))
export IMAGE_SERVICE_PORT=$(( 6016 + $NAMESPACE_INDEX ))
export IMAGE_SERVICE_BASE_URL=${SERVICE_BASE_URL:-"http://${SERVICE_URL}:${IMAGE_SERVICE_PORT}"}
export SERVICE_INTERNAL_PORT=8090
export IMAGE_SERVICE_INTERNAL_PORT=8080
export SERVICE_BASE_URL=${SERVICE_BASE_URL:-"http://${SERVICE_URL}:${SERVICE_PORT}"}
export EXTERNAL_PORT=${EXTERNAL_PORT:-y}
export OCP_SERVICE_PORT=$(( 7000 + $NAMESPACE_INDEX ))
export OPENSHIFT_INSTALL_RELEASE_IMAGE=${OPENSHIFT_INSTALL_RELEASE_IMAGE:-}
export ENABLE_KUBE_API=${ENABLE_KUBE_API:-false}
export ENABLE_KUBE_API_CMD="ENABLE_KUBE_API=${ENABLE_KUBE_API}"
export DEBUG_SERVICE_NAME=assisted-service-debug
export IMAGE_SERVICE_NAME=assisted-image-service
export DEBUG_SERVICE_PORT=${DEBUG_SERVICE_PORT:-40000}
export DEBUG_SERVICE=${DEBUG_SERVICE:-}
export REGISTRY_SERVICE_NAME=registry
export REGISTRY_SERVICE_NAMESPACE=kube-system
export REGISTRY_SERVICE_PORT=80
export REGISTRY_SERVICE_HOST_PORT=5000


if [[ "${ENABLE_KUBE_API}" == "true" || "${DEPLOY_TARGET}" == "operator" ]]; then
    # Only OS_IMAGES list is required in kube-api flow (assisted-service is using defaults if missing)
    if [ -z "${OPENSHIFT_VERSIONS:-}" ]; then
        export OPENSHIFT_VERSIONS='{}'
    fi
    if [ -z "${RELEASE_IMAGES:-}" ]; then
        export RELEASE_IMAGES='[]'
    fi
fi

mkdir -p build

if [ "${OPENSHIFT_INSTALL_RELEASE_IMAGE}" != "" ]; then
    export RELEASE_IMAGES=$(skipper run ./scripts/override_release_images.py --src ./assisted-service/data/default_release_images.json)
    export OS_IMAGES=$(skipper run ./scripts/override_os_images.py --src ./assisted-service/data/default_os_images.json)

    if [ "${DEPLOY_TARGET}" == "onprem" ]; then
        (cd assisted-service; skipper make generate-configuration)
    fi
fi

if [ "${DEPLOY_TARGET}" == "onprem" ]; then
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

    if [ "${DEBUG_SERVICE}" == "true" ]; then
        # Change the registry service type to LoadBalancer to be able to access it from outside the cluster
        kubectl patch service $REGISTRY_SERVICE_NAME -n $REGISTRY_SERVICE_NAMESPACE --type json -p='[{"op": "replace", "path": "/spec/type", "value":"LoadBalancer"}]'
        # Forward the minikube registry addon k8s service to the host to push the debug image using localhost:5000
        spawn_port_forwarding_command $REGISTRY_SERVICE_NAME $REGISTRY_SERVICE_HOST_PORT $REGISTRY_SERVICE_NAMESPACE 999 $KUBECONFIG minikube undeclaredip $REGISTRY_SERVICE_PORT $REGISTRY_SERVICE_NAME
        # Set the local registry to the minikube registry (used by the assisted-service update-local-image target)
        export LOCAL_ASSISTED_ORG=localhost:5000
        print_log "Patching assisted service image with a debuggable code "
        (cd assisted-service/ && skipper --env-file ../skipper.env make update-local-image -e CONTAINER_BUILD_EXTRA_PARAMS="--cgroup-manager=cgroupfs --storage-driver=vfs --events-backend=file")
        DEBUG_DEPLOY_AI_PARAMS="REPLICAS_COUNT=1"
        # Override the SERVICE environment variable with the local registry debug image
        export SERVICE="${LOCAL_ASSISTED_ORG}/assisted-service:latest"
    fi

    skipper run src/update_assisted_service_cm.py
    (cd assisted-service/ && skipper --env-file ../skipper.env run "make deploy-all" ${SKIPPER_PARAMS} $ENABLE_KUBE_API_CMD DEPLOY_TAG=${DEPLOY_TAG} DEPLOY_MANIFEST_PATH=${DEPLOY_MANIFEST_PATH} DEPLOY_MANIFEST_TAG=${DEPLOY_MANIFEST_TAG} NAMESPACE=${NAMESPACE} AUTH_TYPE=${AUTH_TYPE} ${DEBUG_DEPLOY_AI_PARAMS:-})

    add_firewalld_port $SERVICE_PORT

    print_log "Starting port forwarding for deployment/${SERVICE_NAME} on port $SERVICE_PORT"
    wait_for_url_and_run ${SERVICE_BASE_URL} "spawn_port_forwarding_command $SERVICE_NAME $SERVICE_PORT $NAMESPACE $NAMESPACE_INDEX $KUBECONFIG minikube undeclared $SERVICE_INTERNAL_PORT"

    if [ "${DEBUG_SERVICE}" == "true" ]; then
        # delve stops all the thread/goroutines once a breakpoint hits which cause the health call to fail and kubernetes reboots the containers.
        # see: https://github.com/go-delve/delve/issues/777
        print_log "Removing liveness Probe to prevent rebooting while debugging"
        kubectl patch deployment assisted-service -n $NAMESPACE --type json   -p='[{"op": "remove", "path": "/spec/template/spec/containers/0/livenessProbe"}]'

        add_firewalld_port ${DEBUG_SERVICE_PORT}
        print_log "Starting port forwarding for deployment/${SERVICE_NAME} on debug port $DEBUG_SERVICE_PORT"
        spawn_port_forwarding_command $SERVICE_NAME $DEBUG_SERVICE_PORT $NAMESPACE $NAMESPACE_INDEX $KUBECONFIG minikube undeclaredip $DEBUG_SERVICE_PORT $DEBUG_SERVICE_NAME
    fi

    add_firewalld_port ${IMAGE_SERVICE_PORT}
    print_log "Starting port forwarding for deployment/${IMAGE_SERVICE_NAME} on debug port $IMAGE_SERVICE_PORT"
    spawn_port_forwarding_command $IMAGE_SERVICE_NAME $IMAGE_SERVICE_PORT $NAMESPACE $NAMESPACE_INDEX $KUBECONFIG minikube undeclaredip $IMAGE_SERVICE_INTERNAL_PORT $IMAGE_SERVICE_NAME

    print_log "${SERVICE_NAME} can be reached at ${SERVICE_BASE_URL} "
    print_log "Done"
fi
