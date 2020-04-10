BMI_BRANCH ?= master
IMAGE ?= ""
NODES_COUNT ?= 4
WORKER_MEMORY ?= 8192
MASTER_MEMORY ?= 8192
STORAGE_POOL_PATH ?= $(PWD)/storage_pool
SSH_KEY ?= "ssh_key/key.pub"
SHELL=/bin/sh
CURRENT_USER=$(shell id -u $(USER))

.PHONY: image_build run destroy start_minikube delete_minikube run destroy install_minikube deploy_bm_inventory create_environment

image_build:
	docker pull quay.io/itsoiref/test-infra:latest && docker image tag quay.io/itsoiref/test-infra:latest test-infra:latest || docker build -t test-infra -f Dockerfile.test-infra .

create_full_environment:
	scripts/install_environment.sh
	$(MAKE) image_build
	skipper make bring_bm_inventory
	$(MAKE) start_minikube

create_environment:
	$(MAKE) image_build
	skipper make bring_bm_inventory
	$(MAKE) start_minikube

clean:
	rm -rf build
	rm -rf bm-inventory

install_minikube:
	scripts/install_minikube.sh

start_minikube: install_minikube
	scripts/run_minikube.sh
	eval $(minikube docker-env)

delete_minikube:
	minikube delete
	scripts/virsh_cleanup.py -m

copy_terraform_files:
	mkdir -p build/terraform
	FILE=build/terraform/terraform.tfvars.json
	@if [ ! -f "build/terraform/terraform.tfvars.json" ]; then\
		cp -r terraform_files/* build/terraform/;\
	fi

create_network: copy_terraform_files
	cd build/terraform/network && terraform init  -plugin-dir=/root/.terraform.d/plugins/ && terraform apply -auto-approve -input=false -state=terraform.tfstate -state-out=terraform.tfstate -var-file=../terraform.tfvars.json

destroy_network:
	cd build/terraform/network  && terraform destroy -auto-approve -input=false -state=terraform.tfstate -state-out=terraform.tfstate -var-file=../terraform.tfvars.json || echo "Failed cleanup network"

run_terraform: copy_terraform_files
	cd build/terraform/ && terraform init  -plugin-dir=/root/.terraform.d/plugins/ && terraform apply -auto-approve -input=false -state=terraform.tfstate -state-out=terraform.tfstate -var-file=terraform.tfvars.json

destroy_terraform:
	cd build/terraform/  && terraform destroy -auto-approve -input=false -state=terraform.tfstate -state-out=terraform.tfstate -var-file=terraform.tfvars.json || echo "Failed, cleanup will help"
	scripts/virsh_cleanup.py -sm

run: start_minikube deploy_bm_inventory

run_full_flow: run deploy_nodes

deploy_nodes:
	discovery-infra/start_discovery.py -i $(IMAGE) -n $(NODES_COUNT) -p $(STORAGE_POOL_PATH) -k $(SSH_KEY) -mm $(MASTER_MEMORY) -wm $(WORKER_MEMORY)

destroy_nodes:
	discovery-infra/delete_nodes.py

destroy: destroy_terraform delete_minikube
	rm -rf build/terraform/*
	scripts/virsh_cleanup.py -a

deploy_bm_inventory: bring_bm_inventory
	make -C bm-inventory/ deploy-all

bring_bm_inventory:
	@if cd bm-inventory; then git fetch --all && git reset --hard origin/$(BMI_BRANCH); else git clone --branch $(BMI_BRANCH) https://github.com/filanov/bm-inventory;fi

clear_inventory:
	make -C bm-inventory/ clear-deployment

create_inventory_client: bring_bm_inventory
	mkdir -p build
	echo '{"packageName" : "bm_inventory_client", "packageVersion": "1.0.0"}' > build/code-gen-config.json
	sed -i '/pattern:/d' $(PWD)/bm-inventory/swagger.yaml
	docker run -it --rm -u $(CURRENT_USER) -v $(PWD)/build:/swagger-api/out -v $(PWD)/bm-inventory/swagger.yaml:/swagger.yaml:ro -v $(PWD)/build/code-gen-config.json:/config.json:ro jimschubert/swagger-codegen-cli:2.3.1 generate --lang python --config /config.json --output ./bm-inventory-client/ --input-spec /swagger.yaml
