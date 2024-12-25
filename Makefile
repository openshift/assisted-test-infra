#############
# Variables #
#############

SHELL=/bin/sh
CONTAINER_COMMAND := $(shell scripts/utils.sh get_container_runtime_command)

# Selecting the right podman-remote version since podman-remote4 cannot work against podman-server3 and vice versa.
# It must be occurred before any other container related task.
# Makefile syntax force us to assign the shell result to a variable - please ignore it.
PODMAN_CLIENT_SELECTION_IGNORE_ME := $(shell scripts/utils.sh select_podman_client)

ROOT_DIR = $(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))
PYTHONPATH := ${PYTHONPATH}:${ROOT_DIR}/src
PATH := ${PATH}:/usr/local/bin

REPORTS = $(ROOT_DIR)/reports
TEST_SESSION_ID=$(shell mktemp -u "XXXXXXXXX")
PYTEST_JUNIT_FILE="${REPORTS}/unittest_${TEST_SESSION_ID}.xml"
PYTEST_FLAGS := $(or ${PYTEST_FLAGS}, --error-for-skips)

SKIPPER_PARAMS ?= -i

ASSISTED_SERVICE_HOST := $(or ${ASSISTED_SERVICE_HOST},$(shell hostname))

# Openshift CI params
OPENSHIFT_CI := $(or ${OPENSHIFT_CI}, "false")
JOB_TYPE := $(or ${JOB_TYPE}, "")
REPO_NAME := $(or ${REPO_NAME}, "")
PULL_NUMBER := $(or ${PULL_NUMBER}, "")

CONTAINER_RUNTIME_COMMAND := $(or ${CONTAINER_COMMAND}, ${CONTAINER_RUNTIME_COMMAND})

# lint
LINT_CODE_STYLING_DIRS := src/tests src/triggers src/assisted_test_infra/test_infra src/assisted_test_infra/download_logs src/service_client src/consts src/virsh_cleanup src/cli

# assisted-service
SERVICE := $(or $(SERVICE), quay.io/edge-infrastructure/assisted-service:latest)
SERVICE_NAME := $(or $(SERVICE_NAME),assisted-service)
INDEX_IMAGE := $(or ${INDEX_IMAGE},quay.io/edge-infrastructure/assisted-service-index:latest)
REMOTE_SERVICE_URL := $(or $(REMOTE_SERVICE_URL), "")
USE_LOCAL_SERVICE := $(or $(USE_LOCAL_SERVICE), false)
DEBUG_SERVICE := $(or $(DEBUG_SERVICE), "")

# terraform
TF_LOG_PATH=$(REPORTS)/terraform_$(TEST_SESSION_ID).log
TF_LOG=json

# ui service
UI_SERVICE_NAME := $(or $(UI_SERVICE_NAME),assisted-installer-ui)

# Monitoring services
PROMETHEUS_SERVICE_NAME := $(or $(PROMETHEUS_SERVICE_NAME),prometheus-k8s)

# network params
NAMESPACE := $(or $(NAMESPACE),assisted-installer)
BASE_DNS_DOMAINS := $(or $(BASE_DNS_DOMAINS), "")
BASE_DOMAIN := $(or $(BASE_DOMAIN),redhat.com)

# secrets
SSH_PUB_KEY := $(or $(SSH_PUB_KEY),$(shell cat ~/.ssh/id_rsa.pub))
PULL_SECRET :=  $(or $(PULL_SECRET), $(shell if ! [ -z "${PULL_SECRET_FILE}" ];then cat ${PULL_SECRET_FILE};fi))
ROUTE53_SECRET := $(or $(ROUTE53_SECRET), "")
OFFLINE_TOKEN := $(or $(OFFLINE_TOKEN), "")
SERVICE_ACCOUNT_CLIENT_ID := $(or $(SERVICE_ACCOUNT_CLIENT_ID), "")
SERVICE_ACCOUNT_CLIENT_SECRET := $(or $(SERVICE_ACCOUNT_CLIENT_SECRET), "")
OCM_CLI_REFRESH_TOKEN := $(or $(OCM_CLI_REFRESH_TOKEN), "")

# deploy
DEPLOY_TAG := $(or $(DEPLOY_TAG), "")
DEPLOY_MANIFEST_PATH := $(or $(DEPLOY_MANIFEST_PATH), "")
DEPLOY_MANIFEST_TAG := $(or $(DEPLOY_MANIFEST_TAG), "")
IMAGE_NAME=assisted-test-infra
LOAD_BALANCER_TYPE := $(or $(LOAD_BALANCER_TYPE), "cluster-managed")

# validate folder
ifeq ($(CURDIR), /root/assisted-test-infra)
    $(error "assisted-test-infra cannot be run directly from /root - it will break the build image mounts and fail to run")
endif

# oc deploy
ifneq ($(or $(OC_MODE),),)
	OC_FLAG := --oc-mode
	OC_TOKEN := $(or $(OC_TOKEN),"")
	OC_SERVER := $(or $(OC_SERVER),https://api.ocp.prod.psi.redhat.com:6443)
	OC_SCHEME := $(or $(OC_SCHEME),http)
	OC_PARAMS = $(OC_FLAG) -oct $(OC_TOKEN) -ocs $(OC_SERVER) --oc-scheme $(OC_SCHEME)
endif

ifdef KEEP_ISO
    KEEP_ISO_FLAG = --keep-iso
endif

ifdef DEBUG
	ifeq ($(DEBUG),pycharm)
	REMOTE_IDE_ADDR:=$(shell echo ${SSH_CLIENT} | cut -f 1 -d " ")
	DEBUG_FLAGS=-m pycharm_remote_debugger -r $(REMOTE_IDE_ADDR) -p 6789
	endif

	ifeq ($(DEBUG),$(filter $(DEBUG),vscode true))
		DEBUG_FLAGS=-m debugpy --listen 0.0.0.0:5678 --wait-for-client
	endif
endif

SSO_URL := $(or $(SSO_URL), https://sso.redhat.com/auth/realms/redhat-external/protocol/openid-connect/token)
OCM_BASE_URL := $(or $(OCM_BASE_URL), https://api.integration.openshift.com/)

DEPLOY_TARGET := $(or $(DEPLOY_TARGET),kind)
OCP_KUBECONFIG := $(or $(OCP_KUBECONFIG),build/kubeconfig)

IPV6_SUPPORT := $(or ${IPV6_SUPPORT},true)
SERVICE_REPLICAS_COUNT := 3
LSO_DISKS := $(shell echo sd{b..d})
AUTH_TYPE := $(or ${AUTH_TYPE},none)
ENABLE_KUBE_API := $(or ${ENABLE_KUBE_API},false)
ifeq ($(ENABLE_KUBE_API),true)
	SERVICE_REPLICAS_COUNT=1
	AUTH_TYPE=local
endif

ifdef ADDITIONAL_MANIFEST_DIR
	INSTALL_MANIFESTS_DIR=$(ROOT_DIR)/sno-additional-manifests
endif

ifdef BIP_BUTANE_CONFIG
	BOOTSTRAP_INJECT_DIR=$(ROOT_DIR)/sno-bootstrap-manifests/
	BOOTSTRAP_INJECT_MANIFEST=$(BOOTSTRAP_INJECT_DIR}/$(notdir ${BIP_BUTANE_CONFIG}))
endif

.EXPORT_ALL_VARIABLES:


.PHONY: image_build run destroy start_minikube delete_minikube deploy_assisted_service deploy_assisted_operator delete_all_virsh_resources _deploy_assisted_service _destroy_terraform create_hub_cluster delete_hub_cluster delete_kind delete_onprem

###########
# General #
###########

all: setup run deploy_nodes_with_install

destroy: destroy_nodes delete_minikube delete_kind destroy_host_port_forwarding_and_firewall delete_onprem stop_load_balancer

###############
# Environment #
###############
setup:
	./scripts/create_full_environment.sh

create_environment: image_build bring_assisted_service create_hub_cluster

image_build: bring_assisted_service generate_python_client
	$(CONTAINER_COMMAND) build --network=host -t $(IMAGE_NAME) -f Dockerfile.assisted-test-infra .
	$(CONTAINER_COMMAND) tag $(IMAGE_NAME) test-infra:latest  # For backwards computability

create_hub_cluster:
	TARGET=${DEPLOY_TARGET} assisted-service/hack/hub_cluster.sh create

delete_hub_cluster:
	(cd assisted-service && TARGET=${DEPLOY_TARGET} ROOT_DIR=${ROOT_DIR}/assisted-service hack/hub_cluster.sh delete)

clean:
	-python3 ./src/cleanup.py

delete_kind:
	DEPLOY_TARGET=kind $(MAKE) delete_hub_cluster

delete_onprem:
	DEPLOY_TARGET=onprem $(MAKE) delete_hub_cluster

############
# Minikube #
############

start_minikube:
	DEPLOY_TARGET=minikube $(MAKE) create_hub_cluster

delete_clusters:
	TEST=./src/tests/test_targets.py TEST_FUNC=test_delete_clusters $(MAKE) test

delete_minikube:
	skipper run python3 scripts/indexer.py --action del --namespace all $(OC_FLAG)
	DEPLOY_TARGET=minikube $(MAKE) delete_hub_cluster
	skipper run "python3 -m virsh_cleanup"

####################
# Load balancer    #
####################

# Start load balancer if it does not already exist.
# Map the directory $(HOME)/.test-infra/etc/nginx/conf.d to be /etc/nginx/conf.d
# so it will be used by the python code to fill up load balancing definitions
start_load_balancer: stop_load_balancer
	@if [ "$(PLATFORM)" = "none"  ] || [ "$(PLATFORM)" = "external"  ] || [ "${LOAD_BALANCER_TYPE}" = "user-managed" ] || [ "$(START_LOAD_BALANCER)" = "true" ]; then \
		id=$(shell $(CONTAINER_COMMAND) ps --quiet --filter "name=load_balancer"); \
		( test -z "$$id" && echo "Starting load balancer ..." && \
		$(CONTAINER_COMMAND) run -d --rm --dns=127.0.0.1 --net=host --name=load_balancer \
			-v $(HOME)/.test-infra/etc/nginx/conf.d:/etc/nginx/conf.d \
			quay.io/edge-infrastructure/dynamic-load-balancer:latest ) || ! test -z "$$id"; \
	fi

stop_load_balancer:
	@id=$(shell $(CONTAINER_COMMAND) ps --all --quiet --filter "name=load_balancer"); \
	test ! -z "$$id"  && $(CONTAINER_COMMAND) rm -f load_balancer; \
	if [ "$(TEST_TEARDOWN)" != "false" ]; then \
		rm -f  $(HOME)/.test-infra/etc/nginx/conf.d/*.conf >& /dev/null || /bin/true; \
	fi


#############
# Terraform #
#############

_apply_terraform:
		cd build/terraform/$(CLUSTER_NAME)/$(PLATFORM) && \
		terraform apply -auto-approve -input=false -state=terraform.tfstate -state-out=terraform.tfstate -var-file=terraform.tfvars.json

_destroy_terraform:
	cd build/terraform/$(CLUSTER_NAME)/$(PLATFORM) && \
	terraform destroy -auto-approve -input=false -state=terraform.tfstate -state-out=terraform.tfstate -var-file=terraform.tfvars.json

destroy_nodes:
	skipper make $(SKIPPER_PARAMS) _destroy_virsh

_destroy_virsh:
	python3 ${DEBUG_FLAGS} -m virsh_cleanup -f test-infra

destroy_terraform_controller:
	TEST=./src/tests/test_targets.py TEST_FUNC=test_destroy_available_terraform $(MAKE) test;


destroy_nutanix:
	PLATFORM=nutanix make destroy_terraform_controller

destroy_vsphere:
	PLATFORM=vsphere make destroy_terraform_controller

destroy_oci:
	PLATFORM=oci make destroy_terraform_controller

#######
# Run #
#######

validate_namespace:
	scripts/utils.sh validate_namespace $(NAMESPACE)

run: validate_namespace deploy_assisted_service deploy_ui

set_dns:
	scripts/assisted_deployment.sh set_dns $(shell bash scripts/utils.sh get_namespace_index $(NAMESPACE) $(OC_FLAG))

deploy_ui: create_hub_cluster
	NAMESPACE_INDEX=$(shell bash scripts/utils.sh get_namespace_index $(NAMESPACE) $(OC_FLAG)) scripts/deploy_ui.sh

deploy_prometheus_ui:
	NAMESPACE_INDEX=$(shell bash scripts/utils.sh get_namespace_index $(NAMESPACE) $(OC_FLAG)) scripts/deploy_prometheus_ui.sh

test_ui: deploy_ui
	scripts/test_ui.sh

kill_port_forwardings:
	scripts/utils.sh kill_port_forwardings '$(NAMESPACE)'

kill_all_port_forwardings:
	scripts/utils.sh kill_port_forwardings '$(SERVICE_NAME) $(UI_SERVICE_NAME)'
	scripts/utils.sh kill_port_forwardings '$(SERVICE_NAME) $(PROMETHEUS_SERVICE_NAME)'

destroy_host_port_forwarding_and_firewall:
	scripts/utils.sh delete_all_port_forwarding
	firewall-cmd --reload


#########
# Nodes #
#########

deploy_nodes_with_install: start_load_balancer
	@if [ "$(ENABLE_KUBE_API)" = "false"  ]; then \
		TEST_TEARDOWN=no TEST=./src/tests/test_targets.py TEST_FUNC=test_target_install_with_deploy_nodes $(MAKE) test; \
	else \
	    tput setaf 1; echo "Not implemented"; tput sgr0; exit 1; \
	fi

deploy_nodes: start_load_balancer
	TEST_TEARDOWN=no TEST=./src/tests/test_targets.py TEST_FUNC=test_target_deploy_nodes $(MAKE) test

deploy_nodes_with_networking: start_load_balancer
	TEST_TEARDOWN=no TEST=./src/tests/test_targets.py TEST_FUNC=test_target_deploy_networking_with_nodes $(MAKE) test

deploy_static_network_config_nodes:
	make deploy_nodes_with_networking ADDITIONAL_PARAMS="'--with-static-network-config'"

.PHONY: deploy_ibip
deploy_ibip:
ifdef ADDITIONAL_MANIFEST_DIR
	@is_empty_dir=$(shell ls -A ${ADDITIONAL_MANIFEST_DIR}); \
	if [ -n "$$is_empty_dir" ]; then \
		rm -rf ${INSTALL_MANIFEST_DIR}; mkdir ${INSTALL_MANIFESTS_DIR}; \
		mv ${ADDITIONAL_MANIFEST_DIR}/* ${INSTALL_MANIFESTS_DIR}/; \
	fi
endif
	# To deploy with a worker node, set TEST_FUNC=test_bip_add_worker
ifdef BIP_BUTANE_CONFIG
	rm -rf ${BOOTSTRAP_INJECT_DIR}; mkdir ${BOOTSTRAP_INJECT_DIR}
	mv $(dir ${BIP_BUTANE_CONFIG})/* ${BOOTSTRAP_INJECT_DIR}/
endif
	skipper make $(SKIPPER_PARAMS) _test TEST=./src/tests/test_bootstrap_in_place.py TEST_FUNC=$(or ${TEST_FUNC},'test_bootstrap_in_place_sno')

redeploy_nodes: destroy_nodes deploy_nodes_with_networking

redeploy_nodes_with_install: destroy_nodes deploy_nodes_with_install

############
# Operator #
############

clear_operator:
	DISKS="${LSO_DISKS}" ./assisted-service/deploy/operator/destroy.sh

deploy_assisted_operator: clear_operator
	$(MAKE) start_load_balancer START_LOAD_BALANCER=true
	NAMESPACE_INDEX=$(shell bash scripts/utils.sh get_namespace_index $(NAMESPACE) $(OC_FLAG)) DEPLOY_TARGET=operator ./scripts/deploy_assisted_service.sh

#############
# Inventory #
#############

deploy_assisted_service: bring_assisted_service create_hub_cluster
	mkdir -p assisted-service/build
	DEPLOY_TAG=$(DEPLOY_TAG) CONTAINER_COMMAND=$(CONTAINER_COMMAND) NAMESPACE_INDEX=$(shell bash scripts/utils.sh get_namespace_index $(NAMESPACE) $(OC_FLAG)) AUTH_TYPE=$(AUTH_TYPE) DEBUG_FLAGS="${DEBUG_FLAGS}" scripts/deploy_assisted_service.sh

bring_assisted_service:
	./scripts/bring_assisted_service.sh

deploy_monitoring: bring_assisted_service
	ROOT_DIR=$(realpath assisted-service/) make -C assisted-service/ deploy-monitoring
	make deploy_prometheus_ui

delete_all_virsh_resources: destroy_nodes delete_minikube kill_all_port_forwardings

download_service_logs:
	JUNIT_REPORT_DIR=$(REPORTS) ./scripts/download_logs.sh download_service_logs

download_cluster_logs:
	JUNIT_REPORT_DIR=$(REPORTS) ./scripts/download_logs.sh download_cluster_logs

download_capi_logs:
	JUNIT_REPORT_DIR=$(REPORTS) ./scripts/download_logs.sh download_capi_logs

#######
# ISO #
#######

download_iso:
	$(MAKE) test TEST_TEARDOWN=no TEST=./src/tests/test_targets.py TEST_FUNC=test_target_download_iso

########
# Test #
########

$(REPORTS):
	-mkdir -p $(REPORTS)

lint:
	make _flake8

pre-commit:
	# TODO not identifying all pep8 violation - WIP
	mkdir -p build
	pre-commit run --files ./src/assisted_test_infra/test_infra/* ./src/tests/*

_reformat:
	black . --line-length=120
	isort . --profile=black --line-length=120

flake8:
	skipper make _flake8

_flake8:
	flake8 $(FLAKE8_EXTRA_PARAMS) . || (tput setaf 3; echo "If you keep seeing this error[s] try to make reformat"; tput sgr0; exit 1)

reformat:
	FLAKE8_EXTRA_PARAMS="$(FLAKE8_EXTRA_PARAMS)" skipper make _reformat

test:
	$(MAKE) start_load_balancer START_LOAD_BALANCER=true
	skipper make $(SKIPPER_PARAMS) _test

_test: $(REPORTS) _test_setup
	JUNIT_REPORT_DIR=$(REPORTS) python3 ${DEBUG_FLAGS} -m pytest $(PYTEST_FLAGS) $(or ${TEST},src/tests) -k $(or ${TEST_FUNC},'') -m $(or ${TEST_MARKER},'') --verbose -s --junit-xml=$(PYTEST_JUNIT_FILE)

test_parallel:
	$(MAKE) start_load_balancer START_LOAD_BALANCER=true
	skipper make $(SKIPPER_PARAMS) _test_parallel
	scripts/assisted_deployment.sh set_all_vips_dns

_test_setup:
	@if [ "$(TEST_TEARDOWN)" != "false" ]; then \
		rm -rf /tmp/assisted_test_infra_logs; \
		rm -rf /tmp/test_images; \
		rm -f /tmp/tf_network_pool.json; \
	fi
	mkdir -p /tmp/assisted_test_infra_logs

_test_parallel: $(REPORTS) _test_setup
	JUNIT_REPORT_DIR=$(REPORTS) python3 -m pytest $(PYTEST_FLAGS) -n $(or ${TEST_WORKERS_NUM}, '3') $(or ${TEST},src/tests) -k $(or ${TEST_FUNC},'') -m $(or ${TEST_MARKER},'') --verbose -s --junit-xml=$(PYTEST_JUNIT_FILE)

#########
# Tests #
#########
test_kube_api_parallel:
	TEST=./src/tests/test_kube_api.py make test_parallel

cli:
	$(MAKE) start_load_balancer START_LOAD_BALANCER=true
	TEST_TEARDOWN=false JUNIT_REPORT_DIR=$(REPORTS) LOGGING_LEVEL="error" skipper run -i "python3 ${DEBUG_FLAGS} -m src.cli"

validate_client:
	skipper run "python3 ${DEBUG_FLAGS} src/service_client/client_validator.py"

generate_python_client: bring_assisted_service
	cd assisted-service && skipper make generate-python-client
	rm -rf ./.pip && mkdir ./.pip && mv assisted-service/build/assisted-installer/assisted-service-client/dist/*.whl ./.pip/

test_ctlplane_scaleup:
	TEST_TEARDOWN=false TEST=./src/tests/test_ctlplane_scaleup.py TEST_FUNC=test_ctlplane_scaleup $(MAKE) test

install_k8s_api:
	TEST_TEARDOWN=false TEST=./src/tests/test_kube_api.py TEST_FUNC=test_kubeapi $(MAKE) test
