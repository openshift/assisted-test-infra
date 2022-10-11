from typing import Optional
from consts import GB


class OperatorType:
    CNV = "cnv"
    OCS = "ocs"
    ODF = "odf"
    LSO = "lso"
    LVM = "lvm"


class OperatorStatus:
    FAILED = "failed"
    PROGRESSING = "progressing"
    AVAILABLE = "available"


class OperatorResource:
    """operator resource requirements as coded in assisted service"""

    MASTER_MEMORY_KEY: str = "master_memory"
    WORKER_MEMORY_KEY: str = "worker_memory"
    MASTER_VCPU_KEY: str = "master_vcpu"
    WORKER_VCPU_KEY: str = "worker_vcpu"
    MASTER_DISK_KEY: str = "master_disk"
    WORKER_DISK_KEY: str = "worker_disk"
    MASTER_DISK_COUNT_KEY: str = "master_disk_count"
    WORKER_DISK_COUNT_KEY: str = "worker_disk_count"
    MASTER_COUNT_KEY: str = "masters_count"
    WORKER_COUNT_KEY: str = "workers_count"

    @classmethod
    def get_resource_dict(
        cls,
        master_memory: Optional[int] = None,
        worker_memory: Optional[int] = None,
        master_vcpu: Optional[int] = None,
        worker_vcpu: Optional[int] = None,
        master_disk: Optional[int] = None,
        worker_disk: Optional[int] = None,
        master_disk_count: Optional[int] = None,
        worker_disk_count: Optional[int] = None,
        master_count: Optional[int] = None,
        worker_count: Optional[int] = None,
    ) -> dict[str, Optional[int]]:
        return {
            cls.MASTER_MEMORY_KEY: master_memory,
            cls.WORKER_MEMORY_KEY: worker_memory,
            cls.MASTER_VCPU_KEY: master_vcpu,
            cls.WORKER_VCPU_KEY: worker_vcpu,
            cls.MASTER_DISK_KEY: master_disk,
            cls.WORKER_DISK_KEY: worker_disk,
            cls.MASTER_DISK_COUNT_KEY: master_disk_count,
            cls.WORKER_DISK_COUNT_KEY: worker_disk_count,
            cls.MASTER_COUNT_KEY: master_count,
            cls.WORKER_COUNT_KEY: worker_count,
        }

    @classmethod
    def values(cls) -> dict[str, dict[str, Optional[int]]]:
        return {
            OperatorType.CNV: cls.get_resource_dict(master_vcpu=8, worker_vcpu=4),
            OperatorType.OCS: cls.get_resource_dict(
                master_memory=24000,
                worker_memory=24000,
                master_vcpu=12,
                worker_vcpu=12,
                master_disk=10 * GB,
                worker_disk=25 * GB,
                master_disk_count=2,
                worker_disk_count=2,
                worker_count=4,
            ),
            OperatorType.ODF: cls.get_resource_dict(
                master_memory=24000,
                worker_memory=24000,
                master_vcpu=12,
                worker_vcpu=12,
                master_disk=10 * GB,
                worker_disk=25 * GB,
                master_disk_count=2,
                worker_disk_count=2,
                worker_count=4,
            ),
            OperatorType.LSO: cls.get_resource_dict(),
            OperatorType.LVM: cls.get_resource_dict(
                master_count=1,
                master_memory=17600,
                master_vcpu=9,
                master_disk_count=2,
            ),
        }


class OperatorFailedError(Exception):
    """Raised on failed status"""


class CNVOperatorFailedError(OperatorFailedError):
    pass


class OCSOperatorFailedError(OperatorFailedError):
    pass


class ODFOperatorFailedError(OperatorFailedError):
    pass


class LSOOperatorFailedError(OperatorFailedError):
    pass


class LVMOperatorFailedError(OperatorFailedError):
    pass


def get_exception_factory(operator: str) -> OperatorFailedError:
    if operator == OperatorType.CNV:
        return CNVOperatorFailedError

    if operator == OperatorType.OCS:
        return OCSOperatorFailedError

    if operator == OperatorType.ODF:
        return ODFOperatorFailedError

    if operator == OperatorType.LSO:
        return LSOOperatorFailedError

    if operator == OperatorType.LVM:
        return LVMOperatorFailedError

    return OperatorFailedError
