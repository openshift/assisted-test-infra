import json
import logging
import os

from munch import Munch
from test_infra import consts, utils


class Assets:

    def __init__(self, assets_file, lock_file=None):
        self.assets_file = assets_file
        self.lock_file = lock_file or os.path.join("/tmp", os.path.basename(assets_file) + ".lock")
        self._took_assets = []

    def get(self):
        logging.info("Taking asset from %s", self.assets_file)
        with utils.file_lock_context(self.lock_file):
            with open(self.assets_file) as _file:
                all_assets = json.load(_file)
            asset = Munch.fromDict(all_assets.pop(0))
            with open(self.assets_file, "w") as _file:
                json.dump(all_assets, _file)
            self._took_assets.append(asset)
        logging.info("Taken asset: %s", asset)
        return asset

    def release(self, assets):
        logging.info("Returning %d assets", len(assets))
        logging.debug("Assets to return: %s", assets)
        with utils.file_lock_context(self.lock_file):
            with open(self.assets_file) as _file:
                all_assets = json.load(_file)
            all_assets.extend([Munch.toDict(asset) for asset in assets])
            with open(self.assets_file, "w") as _file:
                json.dump(all_assets, _file)

    def release_all(self):
        logging.info("Returning all %d assets", len(self._took_assets))
        self.release(self._took_assets)


class NetworkAssets(Assets):

    def __init__(self):
        super().__init__(assets_file=consts.TF_NETWORK_POOL_PATH)
