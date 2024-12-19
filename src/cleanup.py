import pathlib
import shutil

REMOVE_FILES = ["*.py[co]", "test_infra.log"]
REMOVE_FOLDERS = ["__pycache__", "UNKNOWN.egg-info", "build", "assisted-service", "reports", ".mypy_cache"]


for file in REMOVE_FILES:
    for p in pathlib.Path(".").rglob(file):
        print(f"Removing file {p}")
        p.unlink()

for folder in REMOVE_FOLDERS:
    for p in pathlib.Path(".").rglob(folder):
        print(f"Removing dir {p}")
        shutil.rmtree(p)
