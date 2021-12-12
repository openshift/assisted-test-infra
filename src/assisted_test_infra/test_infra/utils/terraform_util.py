import logging
import os

from assisted_test_infra.test_infra.utils import utils
from consts import consts


class TerraformControllerUtil:
    @classmethod
    def get_folder(cls, cluster_name: str, namespace=None):
        folder_name = f"{cluster_name}__{namespace}" if namespace else f"{cluster_name}"
        return os.path.join(consts.TF_FOLDER, folder_name)

    @classmethod
    def create_folder(cls, cluster_name: str, platform: str):
        tf_folder = cls.get_folder(cluster_name)
        logging.info("Creating %s as terraform folder", tf_folder)
        utils.recreate_folder(tf_folder)
        cls._copy_template_tree(tf_folder, platform)
        return tf_folder

    @classmethod
    def _copy_template_tree(cls, dst, platform: str):
        src = consts.TF_TEMPLATES_ROOT + "/" + platform
        utils.copy_tree(src=src, dst=dst)
