from python_terraform import *


class TerraformUtils:

    def __init__(self, working_dir):
        self.working_dir = working_dir
        self.tf = Terraform(working_dir=working_dir)
        self.tf.init()

    def init_tf(self):
        self.tf.init(**{"plugin-dir": "/root/.terraform.d/plugins"})

    def apply(self):
        self.tf.apply(no_color=IsFlagged, refresh=True, input=True, skip_plan=True)

    def change_variables(self, variables):
        self.tf.apply(no_color=IsFlagged, refresh=True, input=True, var=variables, skip_plan=True)

    def set_new_vip(self, api_vip):
        self.change_variables(variables={"api_vip": api_vip})

    def destroy(self):
        self.tf.destroy(force=True, input=True)
