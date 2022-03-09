class InstallationError(Exception):
    pass


class InstallationFailedError(InstallationError):
    DEFAULT_MESSAGE = "All the nodes must be in valid status, but got some in error"

    def __init__(self, message=DEFAULT_MESSAGE, *args: object) -> None:
        super().__init__(message, *args)


class ReturnedToReadyAfterInstallationStartsError(InstallationError):
    DEFAULT_MESSAGE = "Some nodes returned to ready state after installation was started"

    def __init__(self, message=DEFAULT_MESSAGE, *args: object) -> None:
        super().__init__(message, *args)
