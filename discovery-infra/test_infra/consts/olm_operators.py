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

    WORKER_MEMORY_KEY: str = "worker_memory"
    MASTER_MEMORY_KEY: str = "master_memory"
    WORKER_VCPU_KEY: str = "worker_vcpu"
    MASTER_VCPU_KEY: str = "master_vcpu"
    WORKER_COUNT_KEY: str = "num_workers"
    WORKER_DISK_KEY: str = "worker_disk"

    @classmethod
    def _get_resource_dict(cls, worker_memory: int, master_memory: int, worker_vcpu: int, master_vcpu: int, worker_count: int, worker_disk: int):
        return {
            cls.WORKER_MEMORY_KEY: worker_memory,
            cls.MASTER_MEMORY_KEY: master_memory,
            cls.WORKER_VCPU_KEY: worker_vcpu,
            cls.MASTER_VCPU_KEY: master_vcpu,
            cls.WORKER_COUNT_KEY: worker_count,
            cls.WORKER_DISK_KEY: worker_disk
        }

    @classmethod
    def values(cls) -> dict:
        return {
            OperatorType.CNV:
                cls._get_resource_dict(worker_memory=360, master_memory=150, worker_vcpu=2, master_vcpu=4, worker_count=0, worker_disk=0),
            OperatorType.OCS:
                cls._get_resource_dict(worker_memory=14000, master_memory=24000, worker_vcpu=6, master_vcpu=8, worker_count=3, worker_disk=5368709120),
            OperatorType.LSO:
                cls._get_resource_dict(worker_memory=0, master_memory=0, worker_vcpu=0, master_vcpu=0, worker_count=0, worker_disk=0),
        }
