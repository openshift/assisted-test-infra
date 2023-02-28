import json
import os
import pathlib
from typing import Any, Dict, List

import hcl2
from python_terraform import IsFlagged, Terraform, TerraformCommandError, Tfstate
from retry import retry

from consts import consts
from service_client import log


class _Terraform(Terraform):
    """python_terraform.Terraform always set the force flag (even to false) causing
    destroy failures on some cases. This class overrides the destroy method and set the
    force flag only if it's set to true"""

    def destroy(self, dir_or_plan=None, force=False, **kwargs):
        default = kwargs
        if force:
            default["force"] = force
        options = self._generate_default_options(default)
        args = self._generate_default_args(dir_or_plan)
        return self.cmd("destroy", *args, **options)


class TerraformUtils:
    def __init__(self, working_dir: str, terraform_init: bool = True):
        log.info("TF FOLDER %s ", working_dir)
        self.working_dir = working_dir
        self.var_file_path = os.path.join(working_dir, consts.TFVARS_JSON_NAME)
        self.tf = _Terraform(
            working_dir=working_dir,
            state=consts.TFSTATE_FILE,
            var_file=consts.TFVARS_JSON_NAME,
            is_env_vars_included=True,
        )

        if terraform_init:
            self.init_tf()

    @retry(exceptions=TerraformCommandError, tries=10, delay=10)
    def init_tf(self) -> None:
        self.tf.cmd("init", raise_on_error=True, capture_output=True)

    def select_defined_variables(self, **kwargs):
        supported_variables = self.get_variable_list()
        return {k: v for k, v in kwargs.items() if v is not None and k in supported_variables}

    def get_variable_list(self):
        results = list()

        for tf_file in pathlib.Path(self.working_dir).glob("*.tf"):
            with open(tf_file, "r") as fp:
                terraform_file_dict = hcl2.load(fp)
                results += terraform_file_dict["variable"] if "variable" in terraform_file_dict else list()

        return list(map(lambda d: next(iter(d)), results))

    def apply(self, refresh: bool = True) -> None:
        return_value, output, err = self.tf.apply(no_color=IsFlagged, refresh=refresh, input=False, skip_plan=True)
        if return_value != 0:
            message = f"Terraform apply failed with return value {return_value}, output {output} , error {err}"
            log.error(message)
            raise Exception(message)

    def set_vars(self, **kwargs) -> None:
        defined_variables = self.select_defined_variables(**kwargs)
        self.update_variables_file(defined_variables)

    def set_and_apply(self, refresh: bool = True, **kwargs) -> None:
        self.set_vars(**kwargs)
        self.init_tf()
        self.apply(refresh=refresh)

    def update_variables_file(self, variables: Dict[str, str]):
        with open(self.var_file_path, "r+") as _file:
            tfvars = json.load(_file)
            tfvars.update(variables)
            _file.seek(0)
            _file.truncate()
            json.dump(tfvars, _file)

    def change_variables(self, variables: Dict[str, str], refresh: bool = True) -> None:
        self.update_variables_file(variables=variables)
        self.apply(refresh=refresh)

    def get_state(self) -> Tfstate:
        self.tf.read_state_file(consts.TFSTATE_FILE)
        return self.tf.tfstate

    def get_resources(self, resource_type: str = None) -> List[Dict[str, Any]]:
        state = self.get_state()
        resources = [resource for resource in getattr(state, "resources", {})]
        return [resource for resource in resources if resource_type is None or resource["type"] == resource_type]

    def set_new_vips(self, api_vip: str, ingress_vip: str) -> None:
        self.change_variables(variables={"api_vip": api_vip, "ingress_vip": ingress_vip}, refresh=True)

    def destroy(self, force: bool = True) -> None:
        self.tf.destroy(force=force, input=False, auto_approve=True)
