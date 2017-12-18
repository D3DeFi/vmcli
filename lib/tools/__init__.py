from lib.constants import VM_MIN_MEM, VM_MAX_MEM
from lib.exceptions import VmCLIException


def convert_to_mb(value):
    """Converts size to megabytes."""

    if isinstance(value, str):
        if value.endswith('T'):
            value = int(value.strip('T')) * 1024 * 1024
        elif value.endswith('G'):
            value = int(value.strip('G')) * 1024
        elif value.endswith('M'):
            value = int(value.strip('M'))
        elif value.endswith('K'):
            value = int(value.strip('K')) / 1024
        # Assume bytes otherwise
        else:
            value = int(value) / 1024 / 1024

    try:
        value = int(value)
    except ValueError:
        raise VmCLIException('Unable to convert memory size to gigabytes. Aborting...')

    return value


def normalize_memory(value):
    """Function converts passed value to integer, which will represent size in megabytes
    as well as performs control whether the value sits between global limits."""

    value = convert_to_mb(value)
    if value < VM_MIN_MEM or value > VM_MAX_MEM:
        raise VmCLIException('Memory must be between {}-{} megabytes'.format(VM_MIN_MEM, VM_MAX_MEM))
    else:
        return value
