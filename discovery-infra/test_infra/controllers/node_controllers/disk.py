from enum import Enum

from dataclasses import dataclass


class DiskSourceType(Enum):
    FILE = 1
    NETWORK = 2
    BLOCK = 3
    DIR = 4
    VOLUME = 5
    NVME = 6
    OTHER = 7


@dataclass
class Disk:
    type: str
    alias: str
    wwn: str
    bus: str
    target: str
    source_type: str
    source_path: str
    source_pool: str
    source_volume: str

    def __str__(self):
        return self.target
