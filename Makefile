#############
# Variables #
#############

SHELL=/bin/sh
CONTAINER_COMMAND = $(shell if [ -x "$(shell command -v docker)" ];then echo "docker" ; else echo "podman";fi)
PULL_PARAM=$(shell if [ "${CONTAINER_COMMAND}" = "podman" ];then echo "--pull-always" ; else echo "--pull";fi)

ROOT_DIR = $(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))
PYTHONPATH := ${PYTHONPATH}:${ROOT_DIR}/src
PATH := ${PATH}:/usr/local/bin


REPORTS = $(ROOT_DIR)/reports
PYTEST_JUNIT_FILE=$(shell mktemp -u "$(REPORTS)/unittest_XXXXXXXXX.xml")
SKIPPER_PARAMS ?= -i


ASSISTED_SERVICE_HOST := $(or ${ASSISTED_SERVICE_HOST},$(shell hostname))

# Openshift CI params
OPENSHIFT_CI := $(or ${OPENSHIFT_CI}, "false")
JOB_TYPE := $(or ${JOB_TYPE}, "")
REPO_NAME := $(or ${REPO_NAME}, "")
PULL_NUMBER := $(or ${PULL_NUMBER}, "")

# lint
LINT_CODE_STYLING_DIRS := src/tests src/triggers src/assisted_test_infra/test_infra src/assisted_test_infra/download_logs src/service_client src/consts src/virsh_cleanup src/cli

# assisted-service
SERVICE_BRANCH := $(or $(SERVICE_BRANCH), "master")
SERVICE_BASE_REF := $(or $(SERVICE_BASE_REF), "master")
SERVICE_REPO := $(or $(SERVICE_REPO), "https://github.com/openshift/assisted-service")
SERVICE := $(or $(SERVICE), quay.io/edge-infrastructure/assisted-service:latest)
SERVICE_NAME := $(or $(SERVICE_NAME),assisted-service)
INDEX_IMAGE := $(or ${INDEX_IMAGE},quay.io/edge-infrastructure/assisted-service-index:latest)
REMOTE_SERVICE_URL := $(or $(REMOTE_SERVICE_URL), "")

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

# deploy
DEPLOY_TAG := $(or $(DEPLOY_TAG), "")
DEPLOY_MANIFEST_PATH := $(or $(DEPLOY_MANIFEST_PATH), "")
DEPLOY_MANIFEST_TAG := $(or $(DEPLOY_MANIFEST_TAG), "")
IMAGE_NAME=test-infra


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

DEPLOY_TARGET := $(or $(DEPLOY_TARGET),minikube)
OCP_KUBECONFIG := $(or $(OCP_KUBECONFIG),build/kubeconfig)

PLATFORM := $(or ${PLATFORM},baremetal)
IPV6_SUPPORT := $(or ${IPV6_SUPPORT},true)
SERVICE_REPLICAS_COUNT := 3
LSO_DISKS := $(shell echo sd{b..d})
AUTH_TYPE := $(or ${AUTH_TYPE},none)
ENABLE_KUBE_API := $(or ${ENABLE_KUBE_API},false)
ifeq ($(ENABLE_KUBE_API),true)
	SERVICE_REPLICAS_COUNT=1
	AUTH_TYPE=local
endif

.EXPORT_ALL_VARIABLES:


.PHONY: image_build run destroy start_minikube delete_minikube deploy_assisted_service deploy_assisted_operator delete_all_virsh_resources _deploy_assisted_service _deploy_nodes _destroy_terraform

###########
# General #
###########

all: setup run deploy_nodes_with_install

destroy: destroy_nodes delete_minikube kill_port_forwardings destroy_onprem stop_load_balancer

###############
# Environment #
###############
setup:
	./create_full_environment.sh

create_full_environment: setup  # TODO: remove. only here for compatibility reasons

create_environment: image_build bring_assisted_service start_minikube

image_build:
	sed 's/^FROM .*assisted-service.*:latest/FROM $(subst /,\/,${SERVICE})/' Dockerfile.assisted-test-infra | \
	 $(CONTAINER_COMMAND) build --network=host ${PULL_PARAM} -t $(IMAGE_NAME) -f- .

clean:
	-rm -rf build assisted-service test_infra.log
	-find -name '*.pyc' -delete
	-find -name '*pycache*' -delete

############
# Minikube #
############

start_minikube:
	scripts/run_minikube.sh
	eval $(minikube docker-env)

delete_minikube:
	skipper run python3 scripts/indexer.py --action del --namespace all $(OC_FLAG)
	minikube delete --all
	skipper run "python3 -m virsh_cleanup"

####################
# Podman localhost #
####################

destroy_onprem:
	make -C assisted-service/ clean-onprem || true

####################
# Load balancer    #
####################

# Start load balancer if it does not already exist.
# Map the directory $(HOME)/.test-infra/etc/nginx/conf.d to be /etc/nginx/conf.d
# so it will be used by the python code to fill up load balancing definitions
start_load_balancer:
	@if [ "$(PLATFORM)" = "none"  ] || [ "$(START_LOAD_BALANCER)" = "true" ]; then \
		id=$(shell $(CONTAINER_COMMAND) ps --quiet --filter "name=load_balancer"); \
		( test -z "$$id" && echo "Starting load balancer ..." && \
		$(CONTAINER_COMMAND) run -d --rm --dns=127.0.0.1 --net=host --name=load_balancer \
			-v $(HOME)/.test-infra/etc/nginx/conf.d:/etc/nginx/conf.d \
			quay.io/odepaz/dynamic-load-balancer:latest ) || ! test -z "$$id"; \
	fi

stop_load_balancer:
	@id=$(shell $(CONTAINER_COMMAND) ps --all --quiet --filter "name=load_balancer"); \
	test ! -z "$$id"  && $(CONTAINER_COMMAND) rm -f load_balancer; \
	rm -f  $(HOME)/.test-infra/etc/nginx/conf.d/stream.d/*.conf >& /dev/null || /bin/true


#############
# Terraform #
#############

_apply_terraform:
		cd build/terraform/$(CLUSTER_NAME)/$(PLATFORM) && \
		terraform apply -auto-approve -input=false -state=terraform.tfstate -state-out=terraform.tfstate -var-file=terraform.tfvars.json

destroy_nodes:
	skipper make $(SKIPPER_PARAMS) _destroy_terraform

_destroy_terraform:
	python3 ${DEBUG_FLAGS} -m virsh_cleanup -f test-infra

#######
# Run #
#######

validate_namespace:
	scripts/utils.sh validate_namespace $(NAMESPACE)

run: validate_namespace deploy_assisted_service deploy_ui

set_dns:
	scripts/assisted_deployment.sh set_dns $(shell bash scripts/utils.sh get_namespace_index $(NAMESPACE) $(OC_FLAG))

deploy_ui: start_minikube
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

#########
# Nodes #
#########

deploy_nodes_with_install: start_load_balancer
	@if [ "$(ENABLE_KUBE_API)" = "false"  ]; then \
		TEST_TEARDOWN=no TEST=./src/tests/test_targets.py TEST_FUNC=test_target_install_with_deploy_nodes $(MAKE) test; \
	else \
	    tput setaf 1; echo "Not implemented"; exit 1; \
	fi

deploy_nodes: start_load_balancer
	TEST_TEARDOWN=no TEST=./src/tests/test_targets.py TEST_FUNC=test_target_deploy_nodes $(MAKE) test

deploy_static_network_config_nodes:
	make deploy_nodes ADDITIONAL_PARAMS="'--with-static-network-config'"

deploy_day2_nodes:
	skipper make $(SKIPPER_PARAMS) _deploy_nodes NAMESPACE_INDEX=$(shell bash scripts/utils.sh get_namespace_index $(NAMESPACE) $(OC_FLAG)) NAMESPACE=$(NAMESPACE) $(SKIPPER_PARAMS) ADDITIONAL_PARAMS="'--day2-cloud-cluster'"

deploy_day2_cloud_nodes_with_install:
	skipper make $(SKIPPER_PARAMS) _deploy_nodes NAMESPACE_INDEX=$(shell bash scripts/utils.sh get_namespace_index $(NAMESPACE) $(OC_FLAG)) NAMESPACE=$(NAMESPACE) $(SKIPPER_PARAMS) ADDITIONAL_PARAMS="'-in --day2-cloud-cluster ${ADDITIONAL_PARAMS}'" DEPLOY_TARGET=minikube

deploy_static_network_config_day2_nodes:
	skipper make $(SKIPPER_PARAMS) _deploy_nodes NAMESPACE_INDEX=$(shell bash scripts/utils.sh get_namespace_index $(NAMESPACE) $(OC_FLAG)) NAMESPACE=$(NAMESPACE) $(SKIPPER_PARAMS) ADDITIONAL_PARAMS="'--day2-cloud-cluster --with-static-network-config'"

deploy_static_network_config_day2_nodes_with_install:
	skipper make $(SKIPPER_PARAMS) _deploy_nodes NAMESPACE_INDEX=$(shell bash scripts/utils.sh get_namespace_index $(NAMESPACE) $(OC_FLAG)) NAMESPACE=$(NAMESPACE) $(SKIPPER_PARAMS) ADDITIONAL_PARAMS="'-in --day2-cloud-cluster --with-static-network-config'"

install_day1_and_day2_cloud:
	skipper make $(SKIPPER_PARAMS) _deploy_nodes NAMESPACE_INDEX=$(shell bash scripts/utils.sh get_namespace_index $(NAMESPACE) $(OC_FLAG)) NAMESPACE=$(NAMESPACE) $(SKIPPER_PARAMS) ADDITIONAL_PARAMS="'-in --day2-cloud-cluster --day1-cluster ${ADDITIONAL_PARAMS}'"

deploy_ibip:
	skipper make $(SKIPPER_PARAMS) _test TEST=./src/tests/test_bootstrap_in_place.py

redeploy_nodes: destroy_nodes deploy_nodes

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

deploy_assisted_service: start_minikube bring_assisted_service
	mkdir -p assisted-service/build
	DEPLOY_TAG=$(DEPLOY_TAG) CONTAINER_COMMAND=$(CONTAINER_COMMAND) NAMESPACE_INDEX=$(shell bash scripts/utils.sh get_namespace_index $(NAMESPACE) $(OC_FLAG)) AUTH_TYPE=$(AUTH_TYPE) scripts/deploy_assisted_service.sh

bring_assisted_service:
	@if ! cd assisted-service >/dev/null 2>&1; then \
		git clone $(SERVICE_REPO); \
	fi

ifeq ($(shell [[ $(OPENSHIFT_CI) == "true" && $(REPO_NAME) == "assisted-service" && $(JOB_TYPE) == "presubmit" ]] && echo true),true)
	@echo "Running in assisted-service pull request"
	@cd assisted-service && \
	git fetch origin pull/$(PULL_NUMBER)/head:assisted-service-pr-$(PULL_NUMBER) && \
	git checkout assisted-service-pr-$(PULL_NUMBER)
else
	@cd assisted-service && \
	git fetch --force origin $(SERVICE_BASE_REF):FETCH_BASE $(SERVICE_BRANCH) && \
	git reset --hard FETCH_HEAD && \
	git rebase FETCH_BASE
endif

deploy_monitoring: bring_assisted_service
	make -C assisted-service/ deploy-monitoring
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
	black $(LINT_CODE_STYLING_DIRS) --line-length=120
	isort $(LINT_CODE_STYLING_DIRS) --profile=black --line-length=120

flake8:
	skipper make _flake8

_flake8:
	flake8 $(FLAKE8_EXTRA_PARAMS) $(LINT_CODE_STYLING_DIRS) || (tput setaf 3; echo "If you keep seeing this error[s] try to make reformat"; tput sgr0; exit 1)

reformat:
	FLAKE8_EXTRA_PARAMS="$(FLAKE8_EXTRA_PARAMS)" skipper make _reformat

test:
	$(MAKE) start_load_balancer START_LOAD_BALANCER=true
	skipper make $(SKIPPER_PARAMS) _test

_test: $(REPORTS) _test_setup
	JUNIT_REPORT_DIR=$(REPORTS) python3 ${DEBUG_FLAGS} -m pytest $(or ${TEST},src/tests) -k $(or ${TEST_FUNC},'') -m $(or ${TEST_MARKER},'') --verbose -s --junit-xml=$(PYTEST_JUNIT_FILE)

test_parallel:
	$(MAKE) start_load_balancer START_LOAD_BALANCER=true
	skipper make $(SKIPPER_PARAMS) _test_parallel
	scripts/assisted_deployment.sh set_all_vips_dns

_test_setup:
	rm -rf /tmp/assisted_test_infra_logs
	mkdir /tmp/assisted_test_infra_logs
	rm -rf /tmp/test_images
	rm -f /tmp/tf_network_pool.json

_test_parallel: $(REPORTS) _test_setup
	JUNIT_REPORT_DIR=$(REPORTS) python3 -m pytest -n $(or ${TEST_WORKERS_NUM}, '3') $(or ${TEST},src/tests) -k $(or ${TEST_FUNC},'') -m $(or ${TEST_MARKER},'') --verbose -s --junit-xml=$(PYTEST_JUNIT_FILE)

########
# Capi #
########
deploy_capi_env: start_minikube
	scripts/setup_capi_env.sh


#########
# Tests #
#########
test_kube_api_parallel:
	TEST=./src/tests/test_kube_api.py make test_parallel

cli:
	$(MAKE) start_load_balancer START_LOAD_BALANCER=true
	TEST_TEARDOWN=false JUNIT_REPORT_DIR=$(REPORTS) LOGGING_LEVEL="error" skipper run -i "python3 ${DEBUG_FLAGS} -m src.cli"
