from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, List


@dataclass
class Manifest:
    __ALLOWED_FOLDERS: ClassVar[List[str]] = ["manifests", "openshift"]

    folder: str
    file_name: str
    content: str

    def is_folder_allowed(self) -> bool:
        return self.folder in self.__ALLOWED_FOLDERS

    def get_allowed_folders(self) -> List[str]:
        return deepcopy(self.__ALLOWED_FOLDERS)

    @classmethod
    def get_manifests(cls, path: Path) -> List["Manifest"]:
        manifest_files = []
        if path.is_dir():
            for file_type in ("yaml", "yml", "json"):
                manifest_files.extend(list(path.rglob(f"*.{file_type}")))
        else:
            manifest_files.append(path)

        manifests = []
        for manifest in manifest_files:
            with open(manifest, "rb") as f:
                content = f.read()
            manifests.append(Manifest(folder=manifest.parent.name, file_name=manifest.name, content=content))

        return manifests
