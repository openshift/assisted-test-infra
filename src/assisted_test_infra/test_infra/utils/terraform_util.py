import json
import os
from distutils.dir_util import copy_tree
from pathlib import Path

from consts import consts
from service_client import log


class TerraformControllerUtil:
    @classmethod
    def get_folder(cls, cluster_name: str, namespace=None):
        folder_name = f"{cluster_name}__{namespace}" if namespace else f"{cluster_name}"
        return os.path.join(consts.TF_FOLDER, folder_name)

    @classmethod
    def create_folder(cls, cluster_name: str, platform: str):
        tf_folder = cls.get_folder(cluster_name)
        log.info("Creating %s as terraform folder", tf_folder)
        cls._copy_template_tree(tf_folder)

        tf_folder = os.path.join(tf_folder, platform)
        cls.create_tfvars_file(tf_folder)
        return tf_folder

    @classmethod
    def create_tfvars_file(cls, tf_folder: str) -> str:
        tfvars_file = Path(tf_folder).joinpath(consts.TFVARS_JSON_NAME)

        # Create an empty tfvars file
        with open(tfvars_file, "w") as f:
            json.dump({}, f)

        return str(tfvars_file)

    @classmethod
    def _copy_template_tree(cls, dst: str):
        copy_tree(src=consts.TF_TEMPLATES_ROOT, dst=dst)
