BMI_BRANCH ?= master
IMAGE_PATH ?= /tmp/installer-image-5d2d0e2f-ba40-4b1b-9976-c238cd075d2f.iso
MASTER_COUNT ?= 3

all: build

.PHONY: image-build run destroy start_minikube delete_minikube run destroy install_minikube deploy_bm_inventory deploy_s3
image_build:
	docker build -t test-infra .

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

copy_terraform_files:
	mkdir -p build/terraform
	FILE=build/terraform/terraform.tfvars.json
	@if [ ! -f "build/terraform/terraform.tfvars.json" ]; then\
		cp -r terraform_files/* build/terraform/;\
	fi

create_network: copy_terraform_files
	cd build/terraform/network && terraform init  -plugin-dir=/root/.terraform.d/plugins/ && terraform apply -auto-approve -input=false -state=terraform.tfstate -state-out=terraform.tfstate -var-file=../terraform.tfvars.json

run_terraform: copy_terraform_files
	cd build/terraform/ && terraform init  -plugin-dir=/root/.terraform.d/plugins/ && terraform apply -auto-approve -input=false -state=terraform.tfstate -state-out=terraform.tfstate -var-file=terraform.tfvars.json

destroy_terraform:
	cd build/terraform/  && terraform destroy -auto-approve -input=false -state=terraform.tfstate -state-out=terraform.tfstate -var-file=terraform.tfvars.json || echo "Failed, cleanup will help"

run: create_network start_minikube

run_with_deploy: run deploy_bm_inventory

destroy: destroy_terraform delete_minikube
	scripts/virsh-cleanup.sh
	rm -rf build/terraform/*

create_environment:
	scripts/install_environment.sh

deploy_bm_inventory:
	make -C bm-inventory/ deploy-all

bring_bm_inventory:
	git clone --single-branch --branch $(BMI_BRANCH) https://github.com/filanov/bm-inventory
