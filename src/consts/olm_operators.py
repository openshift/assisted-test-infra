from consts import GB


class OperatorType:
    CNV = "cnv"
    MTV = "mtv"
    ODF = "odf"
    LSO = "lso"
    LVM = "lvm"
    MCE = "mce"
    METALLB = "metallb"
    OPENSHIFT_AI = "openshift-ai"


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
    WORKER_COUNT_KEY: str = "workers_count"

    @classmethod
    def get_resource_dict(
        cls,
        master_memory: int = 0,
        worker_memory: int = 0,
        master_vcpu: int = 0,
        worker_vcpu: int = 0,
        master_disk: int = 0,
        worker_disk: int = 0,
        master_disk_count: int = 0,
        worker_disk_count: int = 0,
        worker_count: int = 0,
    ):
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
    def get_mce_resource_dict(cls, is_sno: bool) -> dict:
        if not is_sno:
            return cls.get_resource_dict(
                master_memory=17000,
                worker_memory=17000,
                master_vcpu=8,
                worker_vcpu=6,
            )
        else:
            return cls.get_resource_dict(
                master_memory=33000,
                master_vcpu=8,
            )

    @classmethod
    def values(cls, is_sno: bool = False) -> dict:
        return {
            OperatorType.CNV: cls.get_resource_dict(master_memory=150, worker_memory=360, master_vcpu=4, worker_vcpu=2),
            OperatorType.MTV: cls.get_resource_dict(
                master_memory=1174, worker_memory=1384, master_vcpu=5, worker_vcpu=3
            ),
            OperatorType.ODF: cls.get_resource_dict(
                master_memory=24000,
                worker_memory=24000,
                master_vcpu=12,
                worker_vcpu=12,
                master_disk=10 * GB,
                worker_disk=25 * GB,
                master_disk_count=1,
                worker_disk_count=1,
                worker_count=4,
            ),
            OperatorType.LSO: cls.get_resource_dict(),
            OperatorType.LVM: cls.get_resource_dict(
                master_memory=1200,
                master_vcpu=1,
                worker_vcpu=1,
                master_disk_count=1,
            ),
            OperatorType.MCE: cls.get_mce_resource_dict(is_sno),
            OperatorType.METALLB: cls.get_resource_dict(),
            OperatorType.OPENSHIFT_AI: cls.get_resource_dict(
                # Note that these requirements are for OpenShift and all its dependencies, in particular ODF.
                master_memory=40 * 1024,
                worker_memory=64 * 1024,
                master_vcpu=12,
                worker_vcpu=20,
                master_disk=100 * GB,
                worker_disk=100 * GB,
                master_disk_count=1,
                worker_disk_count=2,
                worker_count=3,
            ),
        }


class OperatorFailedError(Exception):
    """Raised on failed status"""


class CNVOperatorFailedError(OperatorFailedError):
    pass


class MTVOperatorFailedError(OperatorFailedError):
    pass


class ODFOperatorFailedError(OperatorFailedError):
    pass


class LSOOperatorFailedError(OperatorFailedError):
    pass


class LVMOperatorFailedError(OperatorFailedError):
    pass


class MCEOperatorFailedError(OperatorFailedError):
    pass


class MetalLBOperatorFailedError(OperatorFailedError):
    pass


class OpenShiftAIOperatorFailedError(OperatorFailedError):
    pass


def get_exception_factory(operator: str):

    if operator == OperatorType.CNV:
        return CNVOperatorFailedError

    if operator == OperatorType.MTV:
        return MTVOperatorFailedError

    if operator == OperatorType.ODF:
        return ODFOperatorFailedError

    if operator == OperatorType.LSO:
        return LSOOperatorFailedError

    if operator == OperatorType.LVM:
        return LVMOperatorFailedError

    if operator == OperatorType.MCE:
        return MCEOperatorFailedError

    if operator == OperatorType.METALLB:
        return MetalLBOperatorFailedError

    if operator == OperatorType.OPENSHIFT_AI:
        return OpenShiftAIOperatorFailedError

    return OperatorFailedError


def get_operator_properties(operator: str, **kwargs) -> str:
    if operator == OperatorType.METALLB:
        api_ip = kwargs.get("api_ip")
        ingress_ip = kwargs.get("ingress_ip")
        if api_ip and ingress_ip:
            return f'{{"api_ip": "{api_ip}", "ingress_ip": "{ingress_ip}"}}'

        raise ValueError(f"MetalLB properties are missing or invalid, got {api_ip} {ingress_ip}")

    return ""
