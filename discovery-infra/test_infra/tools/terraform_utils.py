import json
import logging
import os
from typing import Dict

from python_terraform import IsFlagged, Terraform


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
        self.tf.cmd("init -plugin-dir=/root/.terraform.d/plugins/", raise_on_error=True)

    def apply(self, refresh: bool = True) -> None:
        return_value, output, err = self.tf.apply(no_color=IsFlagged, refresh=refresh, input=False, skip_plan=True)
        if return_value != 0:
            message = f"Terraform apply failed with return value {return_value}, output {output} , error {err}"
            logging.error(message)
            raise Exception(message)

    def change_variables(self, variables: Dict[str, str], refresh: bool = True) -> None:
        with open(self.var_file_path, "r+") as _file:
            tfvars = json.load(_file)
            tfvars.update(variables)
            _file.seek(0)
            _file.truncate()
            json.dump(tfvars, _file)
        self.apply(refresh=refresh)

    def get_state(self) -> str:
        self.tf.read_state_file(self.STATE_FILE)
        return self.tf.tfstate

    def set_new_vips(self, api_vip: str, ingress_vip: str) -> None:
        self.change_variables(variables={"api_vip": api_vip, "ingress_vip": ingress_vip}, refresh=True)

    def destroy(self) -> None:
        self.tf.destroy(force=True, input=False, auto_approve=True)
