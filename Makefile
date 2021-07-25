#############
# Variables #
#############

SHELL=/bin/sh
CONTAINER_COMMAND = $(shell if [ -x "$(shell command -v docker)" ];then echo "docker" ; else echo "podman";fi)
PULL_PARAM=$(shell if [ "${CONTAINER_COMMAND}" = "podman" ];then echo "--pull-always" ; else echo "--pull";fi)

ROOT_DIR = $(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))
REPORTS = $(ROOT_DIR)/reports

SKIPPER_PARAMS ?= -i

# assisted-service
SERVICE_BRANCH := $(or $(SERVICE_BRANCH), "master")
SERVICE_BASE_REF := $(or $(SERVICE_BASE_REF), "master")
SERVICE_REPO := $(or $(SERVICE_REPO), "https://github.com/openshift/assisted-service")
SERVICE := $(or $(SERVICE), quay.io/ocpmetal/assisted-service:latest)
SERVICE_NAME := $(or $(SERVICE_NAME),assisted-service)
INDEX_IMAGE := $(or ${INDEX_IMAGE},quay.io/ocpmetal/assisted-service-index:latest)

# assisted-installer
INSTALLER_BRANCH := $(or $(INSTALLER_BRANCH), "master")
INSTALLER_BASE_REF := $(or $(INSTALLER_BASE_REF), "master")
INSTALLER_REPO := $(or $(INSTALLER_REPO), "https://github.com/openshift/assisted-installer")

# ui service
UI_SERVICE_NAME := $(or $(UI_SERVICE_NAME),ocp-metal-ui)

# Monitoring services
PROMETHEUS_SERVICE_NAME := $(or $(PROMETHEUS_SERVICE_NAME),prometheus-k8s)

# nodes params
ISO := $(or $(ISO), "") # ISO should point to a file that has the '.iso' extension. Otherwise deploy will fail!
NUM_MASTERS :=  $(or $(NUM_MASTERS),3)
WORKER_MEMORY ?= 8892
MASTER_MEMORY ?= 16984
NUM_WORKERS := $(or $(NUM_WORKERS),0)
NUM_DAY2_WORKERS := $(or $(NUM_DAY2_WORKERS),1)
STORAGE_POOL_PATH := $(or $(STORAGE_POOL_PATH), $(PWD)/storage_pool)
CLUSTER_ID := $(or $(CLUSTER_ID), "")
CLUSTER_NAME := $(or $(CLUSTER_NAME),test-infra-cluster)
REMOTE_SERVICE_URL := $(or $(REMOTE_SERVICE_URL), "")
WORKER_DISK ?= 21474836480
MASTER_DISK ?= 128849018880
DISABLED_HOST_VALIDATIONS := $(or $(DISABLED_HOST_VALIDATIONS),"")

#hyperthreading
HYPERTHREADING := $(or $(HYPERTHREADING), all)

# network params
NAMESPACE := $(or $(NAMESPACE),assisted-installer)
BASE_DNS_DOMAINS := $(or $(BASE_DNS_DOMAINS), "")
BASE_DOMAIN := $(or $(BASE_DOMAIN),redhat.com)
NETWORK_CIDR := $(or $(NETWORK_CIDR), "")
NETWORK_MTU := $(or $(NETWORK_MTU), 1500)
HTTP_PROXY_URL := $(or $(HTTP_PROXY_URL), "")
HTTPS_PROXY_URL := $(or $(HTTPS_PROXY_URL), "")
NO_PROXY_VALUES := $(or $(NO_PROXY_VALUES), "")
VIP_DHCP_ALLOCATION := $(or $(VIP_DHCP_ALLOCATION),yes)
IPv4 := $(or $(IPv4),yes)
IPv6 := $(or $(IPv6), "")
ISO_IMAGE_TYPE := $(or $(ISO_IMAGE_TYPE), full-iso)

#day2 params
API_VIP_IP := $(or $(API_VIP_IP),"")
API_VIP_DNSNAME := $(or $(API_VIP_DNSNAME),"")

# secrets
SSH_PUB_KEY := $(or $(SSH_PUB_KEY),$(shell cat ssh_key/key.pub))
PULL_SECRET :=  $(or $(PULL_SECRET), $(shell if ! [ -z "${PULL_SECRET_FILE}" ];then cat ${PULL_SECRET_FILE};fi))
ROUTE53_SECRET := $(or $(ROUTE53_SECRET), "")

# elasticsearch
ES_SERVER := $(or $(ES_SERVER), "")
ES_USER := $(or $(ES_USER), "")
ES_PASS := $(or $(ES_PASS), "")
ES_INDEX := $(or $(ES_INDEX), "")
BACKUP_DESTINATION := $(or $(BACKUP_DESTINATION), "")
OFFLINE_TOKEN := $(or $(OFFLINE_TOKEN), "")

# manage
offline_token := $(or $(OFFLINE_TOKEN), "")


# deploy
IMAGE_TAG := latest

DEPLOY_TAG := $(or $(DEPLOY_TAG), "")
DEPLOY_MANIFEST_PATH := $(or $(DEPLOY_MANIFEST_PATH), "")
DEPLOY_MANIFEST_TAG := $(or $(DEPLOY_MANIFEST_TAG), "")
IMAGE_NAME=test-infra
IMAGE_REG_NAME=quay.io/itsoiref/$(IMAGE_NAME)

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

PROXY := $(or $(PROXY),no)

SSO_URL := $(or $(SSO_URL), https://sso.redhat.com/auth/realms/redhat-external/protocol/openid-connect/token)
OCM_BASE_URL := $(or $(OCM_BASE_URL), https://api.integration.openshift.com/)

DEPLOY_TARGET := $(or $(DEPLOY_TARGET),minikube)
OCP_KUBECONFIG := $(or $(OCP_KUBECONFIG),build/kubeconfig)
CONTROLLER_OCP := $(or ${CONTROLLER_OCP},quay.io/ocpmetal/assisted-installer-controller-ocp:latest)

PLATFORM := $(or ${PLATFORM},baremetal)
IPV6_SUPPORT := $(or ${IPV6_SUPPORT},true)
SERVICE_REPLICAS_COUNT := 3
LSO_DISKS := $(shell echo sd{b..d})
AUTH_TYPE := $(or ${AUTH_TYPE},none)
ENABLE_KUBE_API := $(or ${ENABLE_KUBE_API},no)
KUBE_API := $(or ${KUBE_API},no)
ifeq ($(ENABLE_KUBE_API),true)
	SERVICE_REPLICAS_COUNT=1
	KUBE_API=yes
	VIP_DHCP_ALLOCATION=no
	AUTH_TYPE=local
endif

.EXPORT_ALL_VARIABLES:


.PHONY: image_build run destroy start_minikube delete_minikube run destroy deploy_assisted_service deploy_assisted_operator create_environment delete_all_virsh_resources _download_iso _deploy_assisted_service _deploy_nodes  _destroy_terraform

###########
# General #
###########

all: create_full_environment run_full_flow_with_install


destroy: destroy_nodes kill_port_forwardings delete_podman_localhost stop_load_balancer

###############
# Environment #
###############
create_full_environment:
	./create_full_environment.sh

create_environment: image_build bring_assisted_service start_minikube

image_build:
	sed 's/^FROM .*assisted-service.*:latest/FROM $(subst /,\/,${SERVICE})/' Dockerfile.test-infra | \
	 $(CONTAINER_COMMAND) build --network=host ${PULL_PARAM} -t $(IMAGE_NAME):$(IMAGE_TAG) -f- .

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
	skipper run discovery-infra/virsh_cleanup.py -m

####################
# Podman localhost #
####################

delete_podman_localhost:
	make -C assisted-service/ clean-onprem || true

####################
# Load balancer    #
####################

# Start load balancer if it does not already exist.
# Map the directory $(HOME)/.test-infra/etc/nginx/conf.d to be /etc/nginx/conf.d
# so it will be used by the python code to fill up load balancing definitions
start_load_balancer:
	@if [ "$(PLATFORM)" = "none"  ] || [ "$(START_LOAD_BALANCER)" = "true" ]; then \
		id=`podman ps --quiet --filter "name=load_balancer"`; \
		( test -z "$$id" && echo "Staring load balancer ..." && \
		podman run -d --rm --net=host --name=load_balancer \
			-v $(HOME)/.test-infra/etc/nginx/conf.d:/etc/nginx/conf.d \
			load_balancer:latest ) || ! test -z "$$id"; \
	fi

stop_load_balancer:
	@id=`podman ps --quiet --filter "name=load_balancer"`; \
	test ! -z "$$id"  && podman rm -f load_balancer; \
	rm -f  $(HOME)/.test-infra/etc/nginx/conf.d/stream.d/*.conf >& /dev/null || /bin/true


#############
# Terraform #
#############

copy_terraform_files:
	mkdir -p build/terraform/$(CLUSTER_NAME)__$(NAMESPACE)
	FILE=build/terraform/$(CLUSTER_NAME)__$(NAMESPACE)/terraform.tfvars.json
	cp -r terraform_files/* build/terraform/$(CLUSTER_NAME)__$(NAMESPACE);\

run_terraform: copy_terraform_files
	skipper make $(SKIPPER_PARAMS) _run_terraform

_run_terraform:
		cd build/terraform/$(CLUSTER_NAME)__$(NAMESPACE) && \
		terraform init -plugin-dir=/root/.terraform.d/plugins/ && \
		terraform apply -auto-approve -input=false -state=terraform.tfstate -state-out=terraform.tfstate -var-file=terraform.tfvars.json

_apply_terraform:
		cd build/terraform/$(CLUSTER_NAME)__$(NAMESPACE) && \
		terraform apply -auto-approve -input=false -state=terraform.tfstate -state-out=terraform.tfstate -var-file=terraform.tfvars.json

destroy_terraform:
	skipper make $(SKIPPER_PARAMS) _destroy_terraform

_destroy_terraform:
	cd build/terraform/  && terraform destroy -auto-approve -input=false -state=terraform.tfstate -state-out=terraform.tfstate -var-file=terraform.tfvars.json || echo "Failed cleanup terraform"
	discovery-infra/virsh_cleanup.py -f test-infra

#######
# Run #
#######

validate_namespace:
	scripts/utils.sh validate_namespace $(NAMESPACE)

run: validate_namespace deploy_assisted_service deploy_ui

run_full_flow: run deploy_nodes

redeploy_all: destroy run_full_flow

run_full_flow_with_install: run deploy_nodes_with_install

redeploy_all_with_install: destroy run_full_flow_with_install

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

########
# IPv6 #
########
run_full_flow_with_ipv6:
	PULL_SECRET='$(PULL_SECRET)' IPv6=yes IPv4=no VIP_DHCP_ALLOCATION=no PROXY=yes $(MAKE) run_full_flow


#########
# Day 2 #
#########

deploy_on_ocp_cluster: bring_assisted_installer
	# service
	DEPLOY_TARGET=ocp NAMESPACE_INDEX=$(shell bash scripts/utils.sh get_namespace_index $(NAMESPACE)) \
		scripts/deploy_assisted_service.sh

	# UI
	DEPLOY_TARGET=ocp NAMESPACE_INDEX=$(shell bash scripts/utils.sh get_namespace_index $(NAMESPACE)) \
		scripts/deploy_ui.sh

	# controller
	DEPLOY_TARGET=ocp NAMESPACE_INDEX=$(shell bash scripts/utils.sh get_namespace_index $(NAMESPACE)) \
		scripts/deploy_controller.sh

config_etc_hosts_for_ocp_cluster:
	discovery-infra/ocp.py --config-etc-hosts -cn $(CLUSTER_NAME) -ns $(NAMESPACE) --service-name $(SERVICE_NAME) $(ADDITIONAL_PARAMS)

bring_assisted_installer:
	@if ! cd assisted-installer >/dev/null 2>&1; then \
		git clone $(INSTALLER_REPO); \
	fi

	@cd assisted-installer && \
	git fetch --force origin $(INSTALLER_BASE_REF):FETCH_BASE $(INSTALLER_BRANCH) && \
	git reset --hard FETCH_HEAD && \
	git rebase FETCH_BASE

###########
# Cluster #
###########

_install_cluster:
	discovery-infra/install_cluster.py -id $(CLUSTER_ID) -ps '$(PULL_SECRET)' --service-name $(SERVICE_NAME) $(OC_PARAMS) -ns $(NAMESPACE) -cn $(CLUSTER_NAME)

install_cluster:
	skipper make $(SKIPPER_PARAMS) _install_cluster


#########
# Nodes #
#########

_deploy_nodes:
	discovery-infra/start_discovery.py -i $(ISO) -n $(NUM_MASTERS) -p $(STORAGE_POOL_PATH) -k '$(SSH_PUB_KEY)' -md $(MASTER_DISK) -wd $(WORKER_DISK) -mm $(MASTER_MEMORY) -wm $(WORKER_MEMORY) -nw $(NUM_WORKERS) -ps '$(PULL_SECRET)' -bd $(BASE_DOMAIN) -cN $(CLUSTER_NAME) -vN $(NETWORK_CIDR) -nM $(NETWORK_MTU) -iU $(REMOTE_SERVICE_URL) -id $(CLUSTER_ID) -mD $(BASE_DNS_DOMAINS) -ns $(NAMESPACE) -pX $(HTTP_PROXY_URL) -sX $(HTTPS_PROXY_URL) -nX $(NO_PROXY_VALUES) --service-name $(SERVICE_NAME) --vip-dhcp-allocation $(VIP_DHCP_ALLOCATION) --ns-index $(NAMESPACE_INDEX) --deploy-target $(DEPLOY_TARGET) $(DAY1_PARAMS) $(OC_PARAMS) $(KEEP_ISO_FLAG) $(ADDITIONAL_PARAMS) $(DAY2_PARAMS) -ndw $(NUM_DAY2_WORKERS) --ipv4 $(IPv4) --ipv6 $(IPv6) --platform $(PLATFORM) --proxy $(PROXY) --iso-image-type $(ISO_IMAGE_TYPE) --hyperthreading $(HYPERTHREADING) --kube-api $(KUBE_API)

deploy_nodes_with_install: start_load_balancer
	bash scripts/utils.sh local_setup_before_deployment $(PLATFORM) $(NAMESPACE) $(OC_FLAG)
	skipper make $(SKIPPER_PARAMS) _deploy_nodes NAMESPACE_INDEX=$(shell bash scripts/utils.sh get_namespace_index $(NAMESPACE) $(OC_FLAG)) NAMESPACE=$(NAMESPACE) ADDITIONAL_PARAMS="'-in ${ADDITIONAL_PARAMS}'" $(SKIPPER_PARAMS) DAY1_PARAMS=--day1-cluster
	$(MAKE) set_dns

deploy_static_network_config_nodes_with_install:
	make deploy_nodes_with_install ADDITIONAL_PARAMS="'--with-static-network-config'"

deploy_nodes: start_load_balancer
	bash scripts/utils.sh local_setup_before_deployment $(PLATFORM) $(NAMESPACE) $(OC_FLAG)
	skipper make $(SKIPPER_PARAMS) _deploy_nodes NAMESPACE_INDEX=$(shell bash scripts/utils.sh get_namespace_index $(NAMESPACE) $(OC_FLAG)) NAMESPACE=$(NAMESPACE) ADDITIONAL_PARAMS=$(ADDITIONAL_PARAMS) DAY1_PARAMS=--day1-cluster

deploy_static_network_config_nodes:
	make deploy_nodes ADDITIONAL_PARAMS="'--with-static-network-config'"

deploy_day2_nodes:
	skipper make $(SKIPPER_PARAMS) _deploy_nodes NAMESPACE_INDEX=$(shell bash scripts/utils.sh get_namespace_index $(NAMESPACE) $(OC_FLAG)) NAMESPACE=$(NAMESPACE) $(SKIPPER_PARAMS) ADDITIONAL_PARAMS="'--day2-cloud-cluster'"

deploy_day2_cloud_nodes_with_install:
	skipper make $(SKIPPER_PARAMS) _deploy_nodes NAMESPACE_INDEX=$(shell bash scripts/utils.sh get_namespace_index $(NAMESPACE) $(OC_FLAG)) NAMESPACE=$(NAMESPACE) $(SKIPPER_PARAMS) ADDITIONAL_PARAMS="'-in --day2-cloud-cluster ${ADDITIONAL_PARAMS}'" DEPLOY_TARGET=minikube

deploy_day2_ocp_nodes_with_install:
	skipper make $(SKIPPER_PARAMS) _deploy_nodes NAMESPACE_INDEX=$(shell bash scripts/utils.sh get_namespace_index $(NAMESPACE) $(OC_FLAG)) NAMESPACE=$(NAMESPACE) $(SKIPPER_PARAMS) ADDITIONAL_PARAMS="'-in --day2-ocp-cluster'" DEPLOY_TARGET=ocp

deploy_static_network_config_day2_nodes:
	skipper make $(SKIPPER_PARAMS) _deploy_nodes NAMESPACE_INDEX=$(shell bash scripts/utils.sh get_namespace_index $(NAMESPACE) $(OC_FLAG)) NAMESPACE=$(NAMESPACE) $(SKIPPER_PARAMS) ADDITIONAL_PARAMS="'--day2-cloud-cluster --with-static-network-config'"

deploy_static_network_config_day2_nodes_with_install:
	skipper make $(SKIPPER_PARAMS) _deploy_nodes NAMESPACE_INDEX=$(shell bash scripts/utils.sh get_namespace_index $(NAMESPACE) $(OC_FLAG)) NAMESPACE=$(NAMESPACE) $(SKIPPER_PARAMS) ADDITIONAL_PARAMS="'-in --day2-cloud-cluster --with-static-network-config'"

install_day1_and_day2_cloud:
	skipper make $(SKIPPER_PARAMS) _deploy_nodes NAMESPACE_INDEX=$(shell bash scripts/utils.sh get_namespace_index $(NAMESPACE) $(OC_FLAG)) NAMESPACE=$(NAMESPACE) $(SKIPPER_PARAMS) ADDITIONAL_PARAMS="'-in --day2-cloud-cluster --day1-cluster ${ADDITIONAL_PARAMS}'"

destroy_nodes:
	skipper run $(SKIPPER_PARAMS) 'discovery-infra/delete_nodes.py -iU $(REMOTE_SERVICE_URL) -id $(CLUSTER_ID) -ns $(NAMESPACE) --service-name $(SERVICE_NAME) -cn $(CLUSTER_NAME) $(OC_PARAMS) --kube-api $(KUBE_API)'
	rm -rf build/terraform/$(CLUSTER_NAME)__$(NAMESPACE)

destroy_all_nodes_from_namespaces:
	skipper run $(SKIPPER_PARAMS) 'discovery-infra/delete_nodes.py -iU $(REMOTE_SERVICE_URL) -id $(CLUSTER_ID) -cn $(CLUSTER_NAME) --service-name $(SERVICE_NAME) $(OC_PARAMS) -ns all --kube-api $(KUBE_API)'

destroy_all_nodes:
	skipper run $(SKIPPER_PARAMS) 'discovery-infra/delete_nodes.py --delete-all --kube-api $(KUBE_API)'

deploy_ibip: _test_setup
ifdef SKIPPER_USERNAME
	$(error Running this target using skipper is not supported, try `make deploy_ibip` instead)
endif
	skipper make $(SKIPPER_PARAMS) _deploy_nodes $(SKIPPER_PARAMS) ADDITIONAL_PARAMS="'--bootstrap-in-place'" NUM_WORKERS=0 NUM_MASTERS=1 NAMESPACE_INDEX=0

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

	@cd assisted-service && \
	git fetch --force origin $(SERVICE_BASE_REF):FETCH_BASE $(SERVICE_BRANCH) && \
	git reset --hard FETCH_HEAD && \
	git rebase FETCH_BASE

deploy_monitoring: bring_assisted_service
	make -C assisted-service/ deploy-monitoring
	make deploy_prometheus_ui

delete_all_virsh_resources: destroy_all_nodes delete_minikube kill_all_port_forwardings
	skipper run $(SKIPPER_PARAMS) 'discovery-infra/delete_nodes.py -ns $(NAMESPACE) -a'

download_service_logs:
	./scripts/download_logs.sh download_service_logs

download_cluster_logs:
	./scripts/download_logs.sh download_cluster_logs

##############
# monitoring #
##############

_scrape_service_events:
	discovery-infra/log_scrap.py --inventory-url $(REMOTE_SERVICE_URL) --offline-token $(OFFLINE_TOKEN) --index $(ES_INDEX) -es $(ES_SERVER) -eu $(ES_USER) -ep $(ES_PASS) --backup-destination $(BACKUP_DESTINATION)

scrape_service_events:
	skipper make $(SKIPPER_PARAMS) _scrape_service_events

deploy_elasticsearch:
	docker-compose -f discovery-infra/monitoring/docker-compose.yml up -d

##########
# manage #
##########

_manage_deployment:
	discovery-infra/manage.py --inventory-url=$(REMOTE_SERVICE_URL) --type deregister_clusters --offline-token=$(OFFLINE_TOKEN)

manage_deployment:
	skipper make $(SKIPPER_PARAMS) _manage_deployment

#######
# ISO #
#######

_download_iso:
	discovery-infra/start_discovery.py -k '$(SSH_PUB_KEY)'  -ps '$(PULL_SECRET)' -bd $(BASE_DOMAIN) -cN $(CLUSTER_NAME) -pX $(HTTP_PROXY_URL) -sX $(HTTPS_PROXY_URL) -nX $(NO_PROXY_VALUES) -iU $(REMOTE_SERVICE_URL) -id $(CLUSTER_ID) -mD $(BASE_DNS_DOMAINS) -ns $(NAMESPACE) --service-name $(SERVICE_NAME) --ns-index $(NAMESPACE_INDEX) $(OC_PARAMS) -iO --day1-cluster

download_iso:
	skipper make $(SKIPPER_PARAMS) _download_iso NAMESPACE_INDEX=$(shell bash scripts/utils.sh get_namespace_index $(NAMESPACE) $(OC_FLAG))

download_iso_for_remote_use: deploy_assisted_service
	skipper make $(SKIPPER_PARAMS) _download_iso NAMESPACE_INDEX=$(shell bash scripts/utils.sh get_namespace_index $(NAMESPACE) $(OC_FLAG)) $(OC_FLAG))

########
# Test #
########

$(REPORTS):
	-mkdir -p $(REPORTS)

lint:
	mkdir -p build
	skipper make _lint

_lint:
	pre-commit run --all-files

test:
	$(MAKE) start_load_balancer START_LOAD_BALANCER=true
	skipper make $(SKIPPER_PARAMS) _test

_test: $(REPORTS) _test_setup
	JUNIT_REPORT_DIR=$(REPORTS) python3 ${DEBUG_FLAGS} -m pytest $(or ${TEST},discovery-infra/tests) -k $(or ${TEST_FUNC},'') -m $(or ${TEST_MARKER},'') --verbose -s --junit-xml=$(REPORTS)/unittest.xml

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
	JUNIT_REPORT_DIR=$(REPORTS) python3 -m pytest -n $(or ${TEST_WORKERS_NUM}, '3') $(or ${TEST},discovery-infra/tests) -k $(or ${TEST_FUNC},'') -m $(or ${TEST_MARKER},'') --verbose -s --junit-xml=$(REPORTS)/unittest.xml
