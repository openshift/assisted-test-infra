class OperatorType:
    CNV = "cnv"
    OCS = "ocs"
    LSO = "lso"


class OperatorStatus:
    FAILED = "failed"
    PROGRESSING = "progressing"
    AVAILABLE = "available"


class OperatorResource:
    """ operator resource requirements as coded in assisted service """

    MASTER_MEMORY_KEY: str = "master_memory"
    WORKER_MEMORY_KEY: str = "worker_memory"
    MASTER_VCPU_KEY: str = "master_vcpu"
    WORKER_VCPU_KEY: str = "worker_vcpu"
    MASTER_DISK_KEY: str = "master_disk"
    WORKER_DISK_KEY: str = "worker_disk"
    MASTER_DISK_COUNT_KEY: str = "master_disk_count"
    WORKER_DISK_COUNT_KEY: str = "worker_disk_count"
    WORKER_COUNT_KEY: str = "num_workers"

    @classmethod
    def _get_resource_dict(cls, master_memory: int, worker_memory: int, master_vcpu: int, worker_vcpu: int, master_disk: int, worker_disk: int, master_disk_count: int, worker_disk_count: int, worker_count: int):
        return {
            cls.MASTER_MEMORY_KEY: master_memory,
            cls.WORKER_MEMORY_KEY: worker_memory,
            cls.MASTER_VCPU_KEY: master_vcpu,
            cls.WORKER_VCPU_KEY: worker_vcpu,
            cls.MASTER_DISK_KEY: master_disk,
            cls.WORKER_DISK_KEY: worker_disk,
            cls.MASTER_DISK_COUNT_KEY: master_disk_count,
            cls.WORKER_DISK_COUNT_KEY: worker_disk_count,
            cls.WORKER_COUNT_KEY: worker_count,
        }

    @classmethod
    def values(cls) -> dict:
        return {
            OperatorType.CNV:
                cls._get_resource_dict(master_memory=150, worker_memory=360, master_vcpu=4, worker_vcpu=2, master_disk=0, worker_disk=0, master_disk_count=0, worker_disk_count=0, worker_count=0),
            OperatorType.OCS:
                cls._get_resource_dict(master_memory=24000, worker_memory=24000, master_vcpu=8, worker_vcpu=8, master_disk=10737418240, worker_disk=5368709120, master_disk_count=1, worker_disk_count=1, worker_count=4),
            OperatorType.LSO:
                cls._get_resource_dict(master_memory=0, worker_memory=0, master_vcpu=0, worker_vcpu=0, master_disk=0, worker_disk=0, master_disk_count=0, worker_disk_count=0, worker_count=0),
        }
