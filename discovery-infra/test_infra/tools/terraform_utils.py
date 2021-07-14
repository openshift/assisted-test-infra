import json
import logging
import os
import pathlib
from builtins import list
from typing import Dict

import hcl2
from python_terraform import IsFlagged, Terraform, Tfstate


class TerraformUtils:
    VAR_FILE = "terraform.tfvars.json"
    STATE_FILE = "terraform.tfstate"

    def __init__(self, working_dir: str):
        logging.info("TF FOLDER %s ", working_dir)
        self.working_dir = working_dir
        self.var_file_path = os.path.join(working_dir, self.VAR_FILE)
        self.tf = Terraform(working_dir=working_dir, state=self.STATE_FILE, var_file=self.VAR_FILE)
        self.init_tf()

    def init_tf(self) -> None:
        self.tf.cmd("init", raise_on_error=True)

    def select_defined_variables(self, **kwargs):
        supported_variables = self.get_variable_list()
        return {k: v for k, v in kwargs.items() if v and k in supported_variables}

    def get_variable_list(self):
        results = list()

        for tf_file in pathlib.Path(self.working_dir).glob("*.tf"):
            with open(tf_file, "r") as fp:
                terraform_file_dict = hcl2.load(fp)
                results += terraform_file_dict["variable"] if "variable" in terraform_file_dict else list()

        return list(map(lambda d: next(iter(d)), results))

    def apply(self, refresh: bool = True) -> None:
        return_value, output, err = self.tf.apply(no_color=IsFlagged, refresh=refresh,
                                                  input=False, skip_plan=True)
        if return_value != 0:
            message = f"Terraform apply failed with return value {return_value}, output {output} , error {err}"
            logging.error(message)
            raise Exception(message)

    def set_and_apply(self, refresh: bool = True, **kwargs) -> None:
        defined_variables = self.select_defined_variables(**kwargs)
        self.change_variables(defined_variables)
        self.apply(refresh=refresh)

    def change_variables(self, variables: Dict[str, str], refresh: bool = True) -> None:
        with open(self.var_file_path, "r+") as _file:
            tfvars = json.load(_file)
            tfvars.update(variables)
            _file.seek(0)
            _file.truncate()
            json.dump(tfvars, _file)
        self.apply(refresh=refresh)

    def get_state(self) -> Tfstate:
        self.tf.read_state_file(self.STATE_FILE)
        return self.tf.tfstate

    def get_resources(self, resource_type: str = None) -> list:
        state = self.get_state()
        return [resource for resource in state.resources
                if resource_type is None or resource["type"] == resource_type]

    def set_new_vips(self, api_vip: str, ingress_vip: str) -> None:
        self.change_variables(variables={"api_vip": api_vip, "ingress_vip": ingress_vip}, refresh=True)

    def destroy(self) -> None:
        self.tf.destroy(force=True, input=False, auto_approve=True)
