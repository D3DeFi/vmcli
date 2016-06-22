class VmCLIException(Exception):
    """Base exception for vmcli program."""

    def __init__(self, message):
        super(VmCLIException, self).__init__(message)
