import json
import logging
import os
from typing import List

from munch import Munch
from test_infra import consts, utils


class Assets:
    ASSETS_LOCKFILE_DEFAULT_PATH = "/tmp"

    def __init__(self, assets_file: str, lock_file: str = None):
        self._assets_file: str = assets_file
        self._took_assets: List[Munch] = list()
        self._lock_file: str = lock_file or os.path.join(self.ASSETS_LOCKFILE_DEFAULT_PATH,
                                                         os.path.basename(assets_file) + ".lock")

    def get(self):
        logging.info("Taking asset from %s", self._assets_file)
        with utils.file_lock_context(self._lock_file):
            with open(self._assets_file) as _file:
                all_assets = json.load(_file)
            asset = Munch.fromDict(all_assets.pop(0))
            with open(self._assets_file, "w") as _file:
                json.dump(all_assets, _file)
            self._took_assets.append(asset)
        logging.info("Taken asset: %s", asset)
        return asset

    def _release(self):
        logging.info("Returning %d assets", len(self._took_assets))
        logging.debug("Assets to return: %s", self._took_assets)
        with utils.file_lock_context(self._lock_file):
            with open(self._assets_file) as _file:
                all_assets = json.load(_file)
            all_assets.extend([Munch.toDict(asset) for asset in self._took_assets])
            with open(self._assets_file, "w") as _file:
                json.dump(all_assets, _file)

    def release_all(self):
        logging.info("Returning all %d assets", len(self._took_assets))
        self._release()


class NetworkAssets(Assets):

    def __init__(self):
        super().__init__(assets_file=consts.TF_NETWORK_POOL_PATH)
