#############
# Variables #
#############

SHELL=/bin/sh
CONTAINER_COMMAND = $(shell if [ -x "$(shell command -v docker)" ];then echo "docker" ; else echo "podman";fi)
PULL_PARAM=$(shell if [ "${CONTAINER_COMMAND}" = "podman" ];then echo "--pull-always" ; else echo "--pull";fi)

SKIPPER_PARAMS ?= -i

# assisted-service
SERVICE_BRANCH := $(or $(SERVICE_BRANCH), "master")
SERVICE_REPO := $(or $(SERVICE_REPO), "https://github.com/openshift/assisted-service")
SERVICE := $(or $(SERVICE), quay.io/ocpmetal/assisted-service:latest)

# nodes params
ISO := $(or $(ISO), "") # ISO should point to a file that has the '.iso' extension. Otherwise deploy will fail!
NUM_MASTERS :=  $(or $(NUM_MASTERS),3)
WORKER_MEMORY ?= 8892
MASTER_MEMORY ?= 16984
NUM_WORKERS := $(or $(NUM_WORKERS),0)
STORAGE_POOL_PATH := $(or $(STORAGE_POOL_PATH), $(PWD)/storage_pool)
CLUSTER_ID := $(or $(CLUSTER_ID), "")
CLUSTER_NAME := $(or $(CLUSTER_NAME),test-infra-cluster)
OPENSHIFT_VERSION := $(or $(OPENSHIFT_VERSION), 4.5)
REMOTE_SERVICE_URL := $(or $(REMOTE_SERVICE_URL), "")
WORKER_DISK ?= 21474836480
MASTER_DISK ?= 21474836480

# network params
NAMESPACE := $(or $(NAMESPACE),assisted-installer)
BASE_DNS_DOMAINS := $(or $(BASE_DNS_DOMAINS), "")
BASE_DOMAIN := $(or $(BASE_DOMAIN),redhat.com)
NETWORK_CIDR := $(or $(NETWORK_CIDR),"192.168.126.0/24")
NETWORK_NAME := $(or $(NETWORK_NAME), test-infra-net)
NETWORK_BRIDGE := $(or $(NETWORK_BRIDGE), tt0)
NETWORK_MTU := $(or $(NETWORK_MTU), 1500)
PROXY_URL := $(or $(PROXY_URL), "")
RUN_WITH_VIPS := $(or $(RUN_WITH_VIPS), "yes")

# secrets
SSH_PUB_KEY := $(or $(SSH_PUB_KEY),$(shell cat ssh_key/key.pub))
PULL_SECRET :=  $(or $(PULL_SECRET), $(shell if ! [ -z "${PULL_SECRET_FILE}" ];then cat ${PULL_SECRET_FILE};fi))
ROUTE53_SECRET := $(or $(ROUTE53_SECRET), "")

# deploy
IMAGE_TAG := latest
DEPLOY_TAG := $(or $(DEPLOY_TAG), "")
IMAGE_NAME=test-infra
IMAGE_REG_NAME=quay.io/itsoiref/$(IMAGE_NAME)

.EXPORT_ALL_VARIABLES:


.PHONY: image_build run destroy start_minikube delete_minikube run destroy install_minikube deploy_assisted_service create_environment delete_all_virsh_resources _download_iso _deploy_assisted_service _deploy_nodes  _destroy_terraform

###########
# General #
###########

all: create_full_environment run_full_flow_with_install

destroy: destroy_nodes delete_minikube
	rm -rf build/terraform/*

###############
# Environment #
###############

create_full_environment:
	./create_full_environment.sh

create_environment: image_build bring_assisted_service start_minikube

image_build:
	sed 's/^FROM .*assisted-service.*:latest/FROM $(subst /,\/,${SERVICE})/' Dockerfile.test-infra | \
	 $(CONTAINER_COMMAND) build ${PULL_PARAM} -t $(IMAGE_NAME):$(IMAGE_TAG) -f- .

clean:
	-rm -rf build assisted-service test_infra.log
	-find -name '*.pyc' -delete
	-find -name '*pycache*' -delete

############
# Minikube #
############

install_minikube:
	scripts/install_minikube.sh

start_minikube:
	scripts/run_minikube.sh
	eval $(minikube docker-env)

delete_minikube:
	minikube delete
	skipper run discovery-infra/virsh_cleanup.py -m

#############
# Terraform #
#############

copy_terraform_files:
	mkdir -p build/terraform
	FILE=build/terraform/terraform.tfvars.json
	cp -r terraform_files/* build/terraform/;\

run_terraform: copy_terraform_files
	skipper make _run_terraform $(SKIPPER_PARAMS)

_run_terraform:
		cd build/terraform/ && \
		terraform init -plugin-dir=/root/.terraform.d/plugins/ && \
		terraform apply -auto-approve -input=false -state=terraform.tfstate -state-out=terraform.tfstate -var-file=terraform.tfvars.json

destroy_terraform:
	skipper make _destroy_terraform $(SKIPPER_PARAMS)

_destroy_terraform:
	cd build/terraform/  && terraform destroy -auto-approve -input=false -state=terraform.tfstate -state-out=terraform.tfstate -var-file=terraform.tfvars.json || echo "Failed cleanup terraform"
	discovery-infra/virsh_cleanup.py -f test-infra

#######
# Run #
#######

run: deploy_assisted_service deploy_ui

run_full_flow: run deploy_nodes set_dns

redeploy_all: destroy run_full_flow

run_full_flow_with_install: run deploy_nodes_with_install set_dns

redeploy_all_with_install: destroy  run_full_flow_with_install

set_dns:
	scripts/assisted_deployment.sh set_dns

deploy_ui: start_minikube
	DEPLOY_TAG=$(DEPLOY_TAG) scripts/deploy_ui.sh

test_ui: deploy_ui
	DEPLOY_TAG=$(DEPLOY_TAG) PULL_SECRET=${PULL_SECRET} scripts/test_ui.sh

kill_all_port_forwardings:
	scripts/utils.sh kill_all_port_forwardings

###########
# Cluster #
###########

_install_cluster:
	discovery-infra/install_cluster.py -id $(CLUSTER_ID) -ps '$(PULL_SECRET)' -ns $(NAMESPACE)

install_cluster:
	skipper make _install_cluster NAMESPACE=$(NAMESPACE) $(SKIPPER_PARAMS)


#########
# Nodes #
#########

_deploy_nodes:
	discovery-infra/start_discovery.py -i $(ISO) -n $(NUM_MASTERS) -p $(STORAGE_POOL_PATH) -k '$(SSH_PUB_KEY)' -md $(MASTER_DISK) -wd $(WORKER_DISK) -mm $(MASTER_MEMORY) -wm $(WORKER_MEMORY) -nw $(NUM_WORKERS) -ps '$(PULL_SECRET)' -bd $(BASE_DOMAIN) -cN $(CLUSTER_NAME) -vN $(NETWORK_CIDR) -nN $(NETWORK_NAME) -nB $(NETWORK_BRIDGE) -nM $(NETWORK_MTU) -ov $(OPENSHIFT_VERSION) -rv $(RUN_WITH_VIPS) -iU $(REMOTE_SERVICE_URL) -id $(CLUSTER_ID) -mD $(BASE_DNS_DOMAINS) -ns $(NAMESPACE) $(ADDITIONAL_PARAMS)

deploy_nodes_with_install:
	skipper make _deploy_nodes NAMESPACE=$(NAMESPACE) ADDITIONAL_PARAMS=-in $(SKIPPER_PARAMS)

deploy_nodes:
	skipper make _deploy_nodes NAMESPACE=$(NAMESPACE) $(SKIPPER_PARAMS)

destroy_nodes:
	skipper run 'discovery-infra/delete_nodes.py -iU $(REMOTE_SERVICE_URL) -id $(CLUSTER_ID) -ns $(NAMESPACE)' $(SKIPPER_PARAMS)

redeploy_nodes: destroy_nodes deploy_nodes

redeploy_nodes_with_install: destroy_nodes deploy_nodes_with_install

#############
# Inventory #
#############

deploy_assisted_service: start_minikube bring_assisted_service
	mkdir -p assisted-service/build
	DEPLOY_TAG=$(DEPLOY_TAG) scripts/deploy_assisted_service.sh

bring_assisted_service:
	@if cd assisted-service >/dev/null 2>&1; then git fetch --all && git reset --hard origin/$(SERVICE_BRANCH); else git clone --branch $(SERVICE_BRANCH) $(SERVICE_REPO);fi

deploy_monitoring: bring_assisted_service
	make -C assisted-service/ deploy-monitoring NAMESPACE=$(NAMESPACE)

delete_all_virsh_resources: destroy_nodes delete_minikube
	skipper run 'discovery-infra/delete_nodes.py -ns $(NAMESPACE) -a' $(SKIPPER_PARAMS)

#######
# ISO #
#######

_download_iso:
	discovery-infra/start_discovery.py -k '$(SSH_PUB_KEY)'  -ps '$(PULL_SECRET)' -bd $(BASE_DOMAIN) -cN $(CLUSTER_NAME) -ov $(OPENSHIFT_VERSION) -pU $(PROXY_URL) -iU $(REMOTE_SERVICE_URL) -id $(CLUSTER_ID) -mD $(BASE_DNS_DOMAINS) -ns $(NAMESPACE) -iO

download_iso:
	skipper make _download_iso NAMESPACE=$(NAMESPACE) $(SKIPPER_PARAMS)

download_iso_for_remote_use: deploy_assisted_service
	skipper make _download_iso NAMESPACE=$(NAMESPACE) $(SKIPPER_PARAMS)

########
# Test #
########

lint:
	mkdir -p build
	skipper make _lint

_lint:
	pre-commit run --all-files
