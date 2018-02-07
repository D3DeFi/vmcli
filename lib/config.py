import os
import yaml


def get_config(section, key, env_var, var_type, default=None):
    """Tries to load configuration directive from environment variable or configuration file in
    the exact order. This directives could be overriden via command line arguments."""
    try:
        value = os.getenv(env_var, None)
        if not value:
                section = CONFIG_FILE.get(section, None)
                return var_type(section[key])
        else:
            return var_type(value)
    except (AttributeError, KeyError, TypeError):
        return default
    return default


# If path to configuration file is not provided via environment variable VMCLI_CONFIG_FILE, an attempt is
# made to load locally present file named 'vmcli.yml'.
try:
    CONFIG_FILE = yaml.load(file(os.getenv('VMCLI_CONFIG_FILE', None) or 'vmcli.yml' or ''))
except IOError:
    CONFIG_FILE = None

# Loading of configuration directives is handled by get_config function
# These directives are default settings used within program when used directive is not provided via command line
# Logging configuration directives
LOG_FORMAT          = get_config('logging', 'log_format', 'VMCLI_LOG_FORMAT', str, '%(asctime)s %(levelname)s %(message)s')
LOG_PATH            = get_config('logging', 'log_path', 'VMCLI_LOG_PATH', str, None)
LOG_LEVEL           = get_config('logging', 'log_level', 'VMCLI_LOG_LEVEL', str, 'WARNING')

# Authentication directives
# If password is neither provided via command line or present in ENV variable or configuration file,
# user will be prompted to enter his password after program starts
USERNAME            = get_config('authentication', 'username', 'VMCLI_USERNAME', str, None)
PASSWORD            = get_config('authentication', 'password', 'VMCLI_PASSWORD', str, None)
VCENTER             = get_config('authentication', 'vcenter', 'VMCLI_VCENTER', str, None)
INSECURE_CONNECTION = get_config('authentication', 'insecure_connection', 'VMCLI_INSECURE_CONNECTION', bool, False)

# Timeouts
VM_OS_TIMEOUT       = get_config('timeouts', 'os_timeout', None, int, 120)
VM_TOOLS_TIMEOUT    = get_config('timeouts', 'tools_timeout', None, int, 20)

# Deploy specific directives
# It is recommended to use flavors instead!
# These directives are overriden via command line arguments and flavor settings, the former being preffered
# before the latter.
# Hardware and network configuration will be copied from template if neither command line arguments
# or flavor specification is present.
VM_CPU              = get_config('deploy', 'cpu', 'VMCLI_VM_CPU', int, None)
VM_MEM              = get_config('deploy', 'mem', 'VMCLI_VM_MEM', int, None)
VM_HDD              = get_config('deploy', 'hdd', 'VMCLI_VM_HDD', int, None)
VM_NETWORK          = get_config('deploy', 'network', 'VMCLI_VM_NETWORK', str, None)
VM_NETWORK_CFG      = get_config('deploy', 'network_cfg', 'VMCLI_VM_NETWORK_CFG', str, None)
VM_TEMPLATE         = get_config('deploy', 'template', 'VMCLI_VM_TEMPLATE', str, None)
VM_POWERON          = get_config('deploy', 'poweron', 'VMCLI_VM_POWERON', bool, False)
# If neither command line argument, flavor setting or this global directive is set,
# first usable object will be used, if possible. E.g. first datacenter found in vCenter.
VM_DATACENTER       = get_config('deploy', 'datacenter', 'VMCLI_VM_DATACENTER', str, None)
VM_FOLDER           = get_config('deploy', 'folder', 'VMCLI_VM_FOLDER', str, None)
VM_DATASTORE        = get_config('deploy', 'datastore', 'VMCLI_VM_DATASTORE', str, None)
VM_CLUSTER          = get_config('deploy', 'cluster', 'VMCLI_VM_CLUSTER', str, None)
VM_RESOURCE_POOL    = get_config('deploy', 'resource_pool', 'VMCLI_VM_RESOURCE_POOL', str, None)

VM_ADDITIONAL_CMDS  = get_config('deploy', 'additional_commands', '', list, None)

# Guest information
# Login information used to access guests operating system
VM_GUEST_USER       = get_config('guest', 'guest_user', 'VMCLI_GUEST_USER', str, None)
VM_GUEST_PASS       = get_config('guest', 'guest_pass', 'VMCLI_GUEST_PASS', str, None)
