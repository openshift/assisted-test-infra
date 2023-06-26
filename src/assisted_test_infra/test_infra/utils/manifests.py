from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, List


@dataclass
class Manifest:
    __ALLOWED_FOLDERS: ClassVar[List[str]] = ["manifests", "openshift"]

    folder: str
    file_name: str
    local_path: Path

    def is_folder_allowed(self) -> bool:
        return self.folder in self.__ALLOWED_FOLDERS

    def get_allowed_folders(self) -> List[str]:
        return deepcopy(self.__ALLOWED_FOLDERS)

    @classmethod
    def get_manifests(cls, path: Path) -> List["Manifest"]:
        manifests_files = []

        if path.is_dir():
            for file_type in ("yaml", "yml", "json"):
                manifests_files.extend(list(path.rglob(f"*.{file_type}")))
        else:
            manifests_files.append(path)

        manifests = []
        for file in manifests_files:
            manifests.append(Manifest(folder=file.parent.name, file_name=file.name, local_path=file))

        return manifests
