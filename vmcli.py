#!/usr/bin/env python

import os
import logging
import ConfigParser
import argparse
import ssl
import sys
import atexit
import requests
import netaddr
import time
from collections import OrderedDict


def get_config(section, key, env_var, var_type, default=None):
    """Tries to load configuration directive from environment variable or configuration file in
    the exact order. This directives could be overriden via command line arguments."""
    value = os.getenv(env_var, None)
    if not value:
        if CONFIG_FILE:
            try:
                return var_type(CONFIG_PARSER.get(section, key))
            except (ConfigParser.NoOptionError, ConfigParser.NoSectionError, ValueError):
                return default
    else:
        return value
    return default


def args(*args, **kwargs):
    """Attaches argument to a __dict__ attribute within a specific function or method."""
    # decorator for argument definitions
    def _decorator(func):
        func.__dict__.setdefault('args', []).insert(0, (args, kwargs))
        return func
    return _decorator


# Spawn config file parser
CONFIG_PARSER = ConfigParser.RawConfigParser()
# If path to configuration file is not provided via environment variable VMCLI_CONFIG_FILE, an attempt is
# made to load locally present file named 'vmcli.cfg'.
CONFIG_FILE = CONFIG_PARSER.read(os.getenv('VMCLI_CONFIG_FILE', None) or 'vmcli.cfg')

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
VM_POWERON          = get_config('deploy', 'poweron', 'VMCLI_VM_POWERON', str, True)
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


class VmCLIException(Exception):
    """Base exception for vmcli program."""

    def __init__(self, message):
        super(VmCLIException, self).__init__(message)


class Logger(object):
    """Provides wrapper for loggin.Logger object with option to set logging level across
    all existing instances of Logger class via their shared logging.Handler."""

    def __init__(self, name):
        self.formatter = logging.Formatter(LOG_FORMAT)
        self.handler = self._getHandler(LOG_PATH, self.formatter)
        self.logger = logging.getLogger(name)
        self.logger.addHandler(self.handler)
        self.setLevel(LOG_LEVEL)
        self._quiet = False

    @staticmethod
    def _getHandler(path, formatter_class):
        """Returns appropriate logging.Handler object based on existence of path variable."""
        if path:
            handler = logging.FileHandler(path)
        else:
            handler = logging.StreamHandler()
        # Attach log format defining class to the handler
        handler.setFormatter(formatter_class)
        return handler

    def setLevel(self, lvl):
        log_level = getattr(logging, lvl, None)
        if log_level:
            self.logger.setLevel(log_level)
            self.handler.setLevel(log_level)

    def quiet(self):
        self._quiet = True

    def debug(self, *args, **kwargs):
        if not self._quiet:
            self.logger.debug(*args, **kwargs)

    def info(self, *args, **kwargs):
        if not self._quiet:
            self.logger.info(*args, **kwargs)

    def warning(self, *args, **kwargs):
        if not self._quiet:
            self.logger.warning(*args, **kwargs)

    def error(self, *args, **kwargs):
        if not self._quiet:
            self.logger.error(*args, **kwargs)

    def critical(self, *args, **kwargs):
        if not self._quiet:
            self.logger.critical(*args, **kwargs)


logger = Logger(__name__)

try:
    from pyVmomi import vim, vmodl
    from pyVim.connect import SmartConnect, Disconnect
except ImportError as e:
    logger.critical('{}, make sure it is installed!'.format(e.message))
    sys.exit(1)


# Constants
LOG_LEVEL_CHOICES = ['NOTSET', 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']

VMWARE_TYPES = {
    'vm': vim.VirtualMachine,
    'datacenter': vim.Datacenter,
    'folder': vim.Folder,
    'cluster': vim.ClusterComputeResource,
    'datastore': vim.Datastore,
    'datastore_cluster': vim.StoragePod,
    'resource_pool': vim.ResourcePool,
    'network': vim.dvs.DistributedVirtualPortgroup
}

VM_MIN_CPU = 1
VM_MAX_CPU = 16
VM_MIN_MEM = 256
VM_MAX_MEM = 16384
VM_MIN_HDD = 1
VM_MAX_HDD = 2000


# Flavors
# Use --flavor m1_tiny. To overide this values, simply provide command line arguments
m1_tiny = {
    'name': 'm1.tiny',
    'cpu': 1,
    'mem': 512,
    'hdd': 10,
    'datacenter': 'dc01',
    'folder': 'Production',
    'datastore': 'ds01',
    'cluster': 'cl01',
    'resource_pool': '/Resources',
    'template': 'template.example.com',
    'net': 'dvPortGroup10',
    'net_cfg': '10.1.10.2/24',
    'poweron': True
}


CONNECTION = None
def connect(vcenter=None, username=None, password=None, insecure=None):
    """Creates connection object authenticated against provided vCenter. Created object can be than used
    up to user's permissions to interact with the vCenter via API."""
    # If arguments provided are None, load global directives
    vcenter = vcenter or VCENTER
    username = username or USERNAME
    password = password or PASSWORD
    insecure = insecure or INSECURE_CONNECTION
    # If only password is missing, prompt user interactively
    if (vcenter and username) and not password:
        import getpass
        password = getpass.getpass()
    elif not (vcenter and username and password):
        logger.error('No authentication credentials provided!')
        sys.exit(1)

    sslContext = None
    if insecure:
        requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)
        # Create SSL context for connection without certificate checks
        sslContext = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
        sslContext.verify_mode = ssl.CERT_NONE

    global CONNECTION
    try:
        logger.info('Trying to connect to {} ...'.format(vcenter))
        # Load connection object into global variable
        CONNECTION = SmartConnect(host=vcenter, user=username, pwd=password, sslContext=sslContext)
        # Register function to be executed at termination, eg. session cleanup
        atexit.register(Disconnect, CONNECTION)
        logger.info('Connection successful!')
    except vim.fault.InvalidLogin as e:
        logger.error('Unable to connect. Check your credentials!')
        sys.exit(1)
    except (requests.exceptions.SSLError, requests.exceptions.ConnectionError) as e:
        logger.error(e.message)
        sys.exit(1)


def load_vm_flavor(flavor):
    # TODO: change to import from some appropiate location based on input
    if flavor:
        return m1_tiny
    else:
        return {}


class Worker(object):
    """Class providing interface for various waiting events."""

    def __init__(self):
        global logger
        self.logger = logger
        global CONNECTION
        self.connection = CONNECTION
        if self.connection:
            self.content = self.connection.RetrieveContent()
        else:
            self.content = None

    def wait_for_tasks(self, tasks):
        """Given the service instance content si.content and tasks, function
        returns after all the provided tasks has finished their runs."""
        property_collector = self.content.propertyCollector
        task_list = [str(task) for task in tasks]
        self.logger.debug('Waiting for the following tasks to finish their runs:')
        for task in task_list:
            self.logger.debug('  * {}'.format(task))
        # Create filter
        obj_specs = [vmodl.query.PropertyCollector.ObjectSpec(obj=task) for task in tasks]
        property_spec = vmodl.query.PropertyCollector.PropertySpec(type=vim.Task, pathSet=[], all=True)
        filter_spec = vmodl.query.PropertyCollector.FilterSpec()
        filter_spec.objectSet = obj_specs
        filter_spec.propSet = [property_spec]
        pcfilter = property_collector.CreateFilter(filter_spec, True)
        try:
            version, state = None, None
            # Loop looking for updates till the state moves to a completed state.
            while len(task_list):
                update = property_collector.WaitForUpdates(version)
                for filter_set in update.filterSet:
                    for obj_set in filter_set.objectSet:
                        task = obj_set.obj
                        for change in obj_set.changeSet:
                            if change.name == 'info':
                                state = change.val.state
                            elif change.name == 'info.state':
                                state = change.val
                            else:
                                continue

                            if not str(task) in task_list:
                                continue

                            if state == vim.TaskInfo.State.success:
                                # Remove task from taskList
                                self.logger.debug('Task {} has finished'.format(str(task)))
                                task_list.remove(str(task))
                            elif state == vim.TaskInfo.State.error:
                                raise task.info.error
                # Move to next version
                version = update.version
        finally:
            if pcfilter:
                pcfilter.Destroy()

    def wait_for_guest_os(self, vm, timeout=VM_OS_TIMEOUT):
        """Returns when guest's OS has finished booting up or when timeout is reached."""
        self.logger.info("Waiting for guest's OS to be ready... (timeout {}s)".format(timeout))
        time_wait = 0
        while vm.guest.guestState != 'running':
            if time_wait > timeout:
                self.logger.error("Timeout reached while waiting for vm's OS to boot up...")
                return False
            time.sleep(5)
            time_wait += 5

    def wait_for_guest_vmtools(self, vm, timeout=VM_TOOLS_TIMEOUT):
        """Returns when guest's OS vmtools are running or when timeout is reached."""
        self.logger.info("Waiting for guest's vmtools to be ready... (timeout {}s)".format(timeout))
        time_wait = 0
        while vm.guest.toolsStatus not in ['toolsOk', 'toolsOld']:
            if time_wait > timeout:
                self.logger.error("Timeout reached while waiting for vm's vmtools process...")
                return False
            time.sleep(5)
            time_wait += 5


class BaseCommands(object):
    """Introduces base class for other Commands classes with sharing of same connection content
    and object retrieval. Should be subclassed and its method execute() overriden. Docstring of the
    BaseCommands class should be overriden as well, beacause it will be used as a help for subcommand."""

    def __init__(self):
        global logger
        self.logger = logger
        global CONNECTION
        self.connection = CONNECTION
        if self.connection:
            self.content = self.connection.RetrieveContent()
        else:
            self.content = None
        self.worker = Worker()

    def execute(self, args):
        """Routes to a correct method based on arguments provided. This is also the perfect place
        to define generic arguments, which should be used for every method, via args decorator."""
        raise NotImplementedError("Cannot call super's execute() method! This method must be overidden.")

    def get_obj(self, vimtype, name, default=False):
        """Gets the vsphere object associated with a given text name.
        If default is set to True and name does not match, return first object found."""
        # TODO: make cache or find better way to retreive objects + destroy view object (it is huge in mem)
        # Create container view containing object found
        container = self.content.viewManager.CreateContainerView(self.content.rootFolder, vimtype, True)
        if name is not None:
            self.logger.info('Loading VMware object: {}'.format(name))
            for view in container.view:
                if view.name == name:
                    self.logger.debug('Found matching object {}'.format(view))
                    return view

        # If searched object is not found and default is True, provide first instance found
        if default:
            try:
                return container.view[0]
            except IndexError:
                return None
        return None

    def get_vm_obj(self, name):
        """Gets object associated with the virtual machine name provided and fails if None is found."""
        # Uses hostname provided by vmware tools running on the guest and because of this fact, it is unreliable
        name = name.split('.')[0]
        self.logger.debug('Loading VMware object: {}'.format(name))
        vm = self.content.searchIndex.FindByDnsName(datacenter=None, dnsName=name, vmSearch=True)
        if not vm:
            raise VmCLIException('VM with name {} not found!'.format(name))
        else:
            self.logger.debug('Found matching object {}'.format(vm))
            return vm


class ListCommands(BaseCommands):
    """display specific VMware objects and their details."""

    def __init__(self, *args, **kwargs):
        super(ListCommands, self).__init__(*args, **kwargs)

    @args('type', help='for which type of objects to search', choices=[key for key in VMWARE_TYPES.keys()])
    def execute(self, args):
        if args.name:
            self.show_item([VMWARE_TYPES[args.type]], args.name)
        else:
            self.list_items([VMWARE_TYPES[args.type]])

    def list_items(self, vimtype):
        """Lists items in a specific VMware object category."""
        container = self.content.viewManager.CreateContainerView(self.content.rootFolder, vimtype, True)
        self.logger.info('Searching for requested category...')
        for item in container.view:
            print(item.name)

    @args('--name', help='search for a specific object instead')
    def show_item(self, vimtype, name):
        """Lists details about specific VMware object."""
        # TODO: format output
        # TODO: if vm, use self.get_vm_obj - its faster
        obj = self.get_obj(vimtype, name, default=False)
        if obj:
            print obj.name, obj.configStatus, obj.overallStatus
            # print obj.runtime.powerState
            if obj.parent:
                print obj.parent.name
            if obj.guest:
                print obj.guest.guestId


class CloneCommands(BaseCommands):
    """clone specific VMware objects, without any further configuration."""

    def __init__(self, *args, **kwargs):
        super(CloneCommands, self).__init__(*args, **kwargs)

    @args('--name', required=True, help='name for a cloned object')
    @args('--template', required=True, help='template object to use as a source of cloning')
    def execute(self, args):
        try:
            self.clone_vm(args.name, args.template, args.datacenter, args.folder,
                    args.datastore, args.cluster, args.resource_pool, args.poweron)
        except VmCLIException as e:
            self.logger.error(e.message)
            sys.exit(2)

    @args('--datacenter', help='datacenter where to create vm')
    @args('--folder', help='folder where to place vm')
    @args('--datastore', help='datastore where to store vm')
    @args('--cluster', help='cluster where to spawn mv')
    @args('--resource-pool', help='resource pool, which should be used for vm')
    @args('--poweron', help='whether to power on vm after cloning', action='store_true')
    def clone_vm(self, name, template, datacenter=None, folder=None, datastore=None,
                cluster=None, resource_pool=None, poweron=None):
        """Clones new virtual machine from a template or existing VM."""
        self.logger.info('Running cloning operation...')
        # load provided values or fill them with defaults
        template = template or VM_TEMPLATE
        datacenter = datacenter or VM_DATACENTER
        cluster = cluster or VM_CLUSTER
        folder = folder or VM_FOLDER
        datastore = datastore or VM_DATASTORE
        resource_pool = resource_pool or VM_RESOURCE_POOL
        if poweron is not False:
            poweron = poweron or VM_POWERON
        # Access objects represented by provided names
        try:
            vm = None
            vm = self.get_obj([VMWARE_TYPES['vm']], name)
        except VmCLIException:
            pass
        finally:
            if vm:
                raise VmCLIException('Object with name {} already exists, cannot clone!'.format(name))

        try:
            template = self.get_obj([VMWARE_TYPES['vm']], template)
        except VmCLIException:
            raise VmCLIException('Template {} was not found, cannot clone!'. format(template))

        datacenter = self.get_obj([VMWARE_TYPES['datacenter']], datacenter, default=True)
        self.logger.info('  * Using datacenter {}'.format(datacenter.name))
        cluster = self.get_obj([vim.ClusterComputeResource], cluster, default=True)
        self.logger.info('  * Using cluster {}'.format(cluster.name))
        folder = self.get_obj([VMWARE_TYPES['folder']], folder) or datacenter.vmFolder
        self.logger.info('  * Using folder {}'.format(folder.name))
        datastore = self.get_obj([VMWARE_TYPES['datastore']], datastore or template.datastore[0].info.name)
        self.logger.info('  * Using datastore {}'.format(datastore.name))
        resource_pool = self.get_obj([VMWARE_TYPES['resource_pool']], resource_pool) or cluster.resourcePool
        self.logger.info('  * Using resource pool {}'.format(resource_pool.name))
        # build object with copy specification
        relocspec = vim.vm.RelocateSpec()
        relocspec.datastore = datastore
        relocspec.pool = resource_pool
        # build object with clone specification
        clonespec = vim.vm.CloneSpec()
        clonespec.location = relocspec
        clonespec.powerOn = poweron

        task = template.Clone(folder=folder, name=name, spec=clonespec)
        self.worker.wait_for_tasks([task])


class CreateEmptyVmCommands(BaseCommands):
    """creates empty vm without any guest OS, controllers, disks, floppies, network adapters or cd/dvd drives."""

    def __init__(self, *args, **kwargs):
        super(CreateEmptyVmCommands, self).__init__(*args, **kwargs)

    @args('--name', help='name for a cloned object')
    @args('--flavor', help='flavor to use for a new vm')
    @args('--folder', help='folder where to place vm')
    @args('--resource-pool', help='resource pool, which should be used for vm')
    @args('--datastore', help='datastore where to store vm')
    @args('--mem', help='memory to set for a vm in megabytes', type=int)
    @args('--cpu', help='cpu count to set for a vm', type=int)
    def execute(self, args):
        flavor = load_vm_flavor(args.flavor)
        folder = args.folder or flavor.get('folder', None) or VM_FOLDER
        resource_pool = args.resource_pool or flavor.get('resource_pool', None) or VM_RESOURCE_POOL
        datastore = args.datastore or flavor.get('datastore', None) or VM_DATASTORE
        mem = args.mem or flavor.get('mem', None) or VM_MEM
        cpu = args.cpu or flavor.get('cpu', None) or VM_CPU

        self.create_empty_vm(args.name, folder, resource_pool, datastore, mem, cpu)


    def create_empty_vm(self, name, folder, resource_pool, datastore, mem, cpu):
        """Creates empty vm without disk"""
        if not (name or folder or resource_pool or datastore):
            raise VmCLIException('Missing arguments! Make sure name, folder, resource_pool and datastore are present.')

        # Store logs and snapshots withing same directory as ds_path, which is [datastore]vm_name
        ds_path = '[{}]{}'.format(datastore, name)
        vm_files = vim.vm.FileInfo(logDirectory=None, snapshotDirectory=None, suspendDirectory=None, vmPathName=ds_path)
        # Load cpu and memory configuration
        if not mem:
            mem = VM_MIN_MEM
        elif mem < VM_MIN_MEM or mem > VM_MAX_MEM:
            raise VmCLIException('Memory must be between {}-{}'.format(VM_MIN_MEM, VM_MAX_MEM))

        if not cpu:
            cpu = VM_MIN_CPU
        elif cpu < VM_MIN_CPU or cpu > VM_MAX_CPU:
            raise VmCLIException('CPU count must be between {}-{}'.format(VM_MIN_CPU, VM_MAX_CPU))

        # configuration specification for the new vm, if no mem and cpu is provided, minimal values will be used
        config_spec = vim.vm.ConfigSpec()
        config_spec.name = name
        config_spec.memoryMB = mem
        config_spec.numCPUs = cpu
        config_spec.files = vm_files
        config_spec.guestId = 'otherLinux64Guest'
        config_spec.version = 'vmx-08'

        folder = self.get_obj([VMWARE_TYPES['folder']], folder)
        resource_pool = self.get_obj([VMWARE_TYPES['resource_pool']], resource_pool)
        task = folder.CreateVM_Task(config=config_spec, pool=resource_pool)
        self.worker.wait_for_tasks([task])


class AttachCommands(BaseCommands):
    """attaches specified device to the vm."""
    # TODO: rework attach_net and attach_hdd same as floppy and cdrom (to search for controllers)

    def __init__(self, *args, **kwargs):
        super(AttachCommands, self).__init__(*args, **kwargs)

    @args('--name', help='name of a virtual machine')
    @args('type', help='which type of object to attach', choices=['hdd', 'floppy', 'cdrom', 'network'])
    def execute(self, args):
        try:
            if args.type == 'hdd':
                self.attach_hdd(args.name, args.size)
            elif args.type == 'network':
                self.attach_net_adapter(args.name, args.net)
            elif args.type == 'floppy':
                self.attach_floppy_drive(args.name)
            elif args.type == 'cdrom':
                self.attach_cdrom_drive(args.name)
        except VmCLIException as e:
            self.logger.error(e.message)
            sys.exit(5)

    @args('--size', help='size of a disk to attach in gigabytes (hdd only)', type=int)
    def attach_hdd(self, name, size):
        """Attaches disk to a virtual machine. If no SCSI controller is present, then it is attached as well."""
        if not args.size or args.size < VM_MIN_HDD or args.size > VM_MAX_HDD:
            raise VmCLIException('Hdd size must be between {}-{}'.format(VM_MIN_HDD, VM_MAX_HDD))

        vm = self.get_obj([VMWARE_TYPES['vm']], name)

        disks = []
        controller = None
        # iterate over existing devices and try to find disks and controllerKey
        self.logger.info('Searching for already existing disks and SCSI controllers...')
        for device in vm.config.hardware.device:
            # search for existing SCSI controller or create one if none found
            # TODO: provide flag when to create new controller
            if isinstance(device, vim.vm.device.VirtualSCSIController) and not controller:
                controller = device
            elif isinstance(device, vim.vm.device.VirtualDisk):
                disks.append(device)

        disk_unit_number = 0
        controller_unit_number = 7
        scsispec = None
        # if controller exists, calculate next unit number for disks otherwise create new controller and use defaults
        if controller:
            self.logger.info('Using existing SCSI controller(id:{}) to attach disk'.format(controller.key))
            controller_unit_number = int(controller.key)
            for disk in disks:
                if disk.controllerKey == controller.key and disk_unit_number <= int(device.unitNumber):
                    disk_unit_number = int(device.unitNumber) + 1
        else:
            self.logger.info('No existing SCSI controller found. Creating new one...')
            scsispec = vim.vm.device.VirtualDeviceSpec()
            scsispec.operation = vim.vm.device.VirtualDeviceSpec.Operation.add
            scsispec.device = vim.vm.device.ParaVirtualSCSIController(deviceInfo=vim.Description())
            scsispec.device.slotInfo = vim.vm.device.VirtualDevice.PciBusSlotInfo()
            # if there is no controller on the device present, assign it default values
            scsispec.device.controllerKey = 100
            scsispec.device.unitNumber = 3
            scsispec.device.busNumber = 0
            scsispec.device.hotAddRemove = True
            scsispec.device.sharedBus = 'noSharing'
            scsispec.device.scsiCtlrUnitNumber = controller_unit_number
            controller = scsispec.device
            controller.key = 100

        if disk_unit_number >= 16:
            raise VmCLIException('The SCSI controller does not support any more disks!')
        elif disk_unit_number == 7:
            disk_unit_number =+ 1  # 7 is reserved for SCSI controller itself

        self.logger.info('Creating new empty disk with size {}G'.format(size))
        diskspec = vim.vm.device.VirtualDeviceSpec()
        diskspec.fileOperation = "create"
        diskspec.operation = vim.vm.device.VirtualDeviceSpec.Operation.add
        diskspec.device = vim.vm.device.VirtualDisk()
        diskspec.device.backing = vim.vm.device.VirtualDisk.FlatVer2BackingInfo()
        diskspec.device.backing.diskMode = 'persistent'
        diskspec.device.backing.thinProvisioned = True
        diskspec.device.unitNumber = disk_unit_number
        diskspec.device.capacityInBytes = size * 1024 * 1024 * 1024
        diskspec.device.capacityInKB = size * 1024 * 1024
        diskspec.device.controllerKey = controller.key

        if scsispec:
            dev_change = [scsispec, diskspec]
        else:
            dev_change = [diskspec]

        config_spec = vim.vm.ConfigSpec(deviceChange=dev_change)
        self.logger.info('Attaching device to the virtual machine...')
        task = vm.ReconfigVM_Task(config_spec)
        self.worker.wait_for_tasks([task])

    @args('--net', help='net to attach to a new device (network only)')
    def attach_net_adapter(self, name, net):
        """Attaches virtual network adapter to the vm associated with a VLAN passed via argument."""
        vm = self.get_obj([VMWARE_TYPES['vm']], name)
        nicspec = vim.vm.device.VirtualDeviceSpec()
        nicspec.operation = vim.vm.device.VirtualDeviceSpec.Operation.add
        nicspec.device = vim.vm.device.VirtualVmxnet3(deviceInfo=vim.Description())

        # locate network, which should be assigned to device
        network = self.get_obj([vim.dvs.DistributedVirtualPortgroup], net)
        if not network:
            raise VmCLIException('Unable to find provided network {}'.format(net))

        dvs_port_conn = vim.dvs.PortConnection()
        # use portGroupKey and DVS switch to build connection object
        dvs_port_conn.portgroupKey = network.key
        dvs_port_conn.switchUuid = network.config.distributedVirtualSwitch.uuid

        # specify backing that connects device to a DVS switch portgroup
        nicspec.device.backing = vim.vm.device.VirtualEthernetCard.DistributedVirtualPortBackingInfo()
        nicspec.device.backing.port = dvs_port_conn

        nicspec.device.connectable = vim.vm.device.VirtualDevice.ConnectInfo()
        nicspec.device.connectable.connected = False
        nicspec.device.connectable.startConnected = True
        nicspec.device.connectable.allowGuestControl = True

        config_spec = vim.vm.ConfigSpec(deviceChange=[nicspec])
        self.logger.info('Attaching device to the virtual machine...')
        task = vm.ReconfigVM_Task(config_spec)
        self.worker.wait_for_tasks([task])

    def attach_floppy_drive(self, name):
        """Attaches floppy drive to the virtual machine."""
        vm = self.get_obj([VMWARE_TYPES['vm']], name)
        controller = None
        floppy_device_key = 8000  # 800x reserved for floppies
        # Find Super I/O controller and free device key
        for device in vm.config.hardware.device:
            if isinstance(device, vim.vm.device.VirtualSIOController):
                controller = device
            if isinstance(device, vim.vm.device.VirtualFloppy):
                floppy_device_key = int(device.key) + 1

        floppyspec = vim.vm.device.VirtualDeviceSpec()
        floppyspec.operation = vim.vm.device.VirtualDeviceSpec.Operation.add
        floppyspec.device = vim.vm.device.VirtualFloppy(deviceInfo=vim.Description(
                label='Floppy drive 1', summary='Remote device'))
        floppyspec.device.key = floppy_device_key
        floppyspec.device.controllerKey = controller.key

        floppyspec.device.backing = vim.vm.device.VirtualFloppy.RemoteDeviceBackingInfo(
                deviceName='', useAutoDetect=False)

        floppyspec.device.connectable = vim.vm.device.VirtualDevice.ConnectInfo(
                startConnected=False, allowGuestControl=True, connected=False, status='untried')

        config_spec = vim.vm.ConfigSpec(deviceChange=[floppyspec])
        self.logger.info('Attaching device to the virtual machine...')
        task = vm.ReconfigVM_Task(config_spec)
        self.worker.wait_for_tasks([task])

    def attach_cdrom_drive(self, name):
        """Attaches cd/dvd drive to the virtual machine."""
        vm = self.get_obj([VMWARE_TYPES['vm']], name)
        controller = None
        cdrom_device_key = 3000  # 300x reserved for cd/dvd drives in vmware
        # Find last IDE controller and free device key
        for device in vm.config.hardware.device:
            if isinstance(device, vim.vm.device.VirtualIDEController):
                controller = device
            if isinstance(device, vim.vm.device.VirtualCdrom):
                cdrom_device_key = int(device.key) + 1

        cdspec = vim.vm.device.VirtualDeviceSpec()
        cdspec.operation = vim.vm.device.VirtualDeviceSpec.Operation.add
        cdspec.device = vim.vm.device.VirtualCdrom(deviceInfo=vim.Description(
                label='CD/DVD drive 1', summary='Remote device'))
        cdspec.device.key = cdrom_device_key
        cdspec.device.controllerKey = controller.key

        cdspec.device.backing = vim.vm.device.VirtualCdrom.RemotePassthroughBackingInfo(
                deviceName='', useAutoDetect=False, exclusive=False)

        cdspec.device.connectable = vim.vm.device.VirtualDevice.ConnectInfo(
                startConnected=False, allowGuestControl=True, connected=False, status='untried')

        config_spec = vim.vm.ConfigSpec(deviceChange=[cdspec])
        self.logger.info('Attaching device to the virtual machine...')
        task = vm.ReconfigVM_Task(config_spec)
        self.worker.wait_for_tasks([task])


class ModifyCommands(BaseCommands):
    """modify VMware objects resources or configuration."""

    def __init__(self, *args, **kwargs):
        super(ModifyCommands, self).__init__(*args, **kwargs)

    @args('--name', required=True, help='name of a object to modify')
    def execute(self, args):
        if args.mem or args.cpu:
            try:
                self.change_hw_resource(args.name, args.mem, args.cpu)
            except VmCLIException as e:
                self.logger.error(e.message)
                sys.exit(3)
        elif args.net and args.dev:
            self.change_network(args.name, args.net, args.dev)

    @args('--mem', help='memory to set for a vm in megabytes', type=int)
    @args('--cpu', help='cpu count to set for a vm', type=int)
    def change_hw_resource(self, name, mem=None, cpu=None):
        """Changes hardware resource of a specific VM."""
        vm = self.get_obj([VMWARE_TYPES['vm']], name)
        if not mem and not cpu:
            raise VmCLIException('Neither memory or cpu specified! Cannot run hardware reconfiguration.')

        config_spec = vim.vm.ConfigSpec()
        if mem:
            # TODO: allow to pass --mem 512M or --mem 1G
            if mem < VM_MIN_MEM or mem > VM_MAX_MEM:
                raise VmCLIException('Memory must be between {}-{}'.format(VM_MIN_MEM, VM_MAX_MEM))
            else:
                config_spec.memoryMB = mem

        if cpu:
            if cpu < VM_MIN_CPU or cpu > VM_MAX_CPU:
                raise VmCLIException('CPU count must be between {}-{}'.format(VM_MIN_CPU, VM_MAX_CPU))
            else:
                config_spec.numCPUs = cpu

        self.logger.info("Setting vm's resources according to specification...")
        task = vm.ReconfigVM_Task(config_spec)
        self.worker.wait_for_tasks([task])

    @args('--net', help='network to attach to a network device')
    @args('--dev', help='device to attach provided network to')
    def change_network(self, name, net, dev):
        """Changes network associated with a specifc VM's network interface."""
        vm = self.get_obj([VMWARE_TYPES['vm']], name)
        nicspec = None
        # search for Ethernet devices
        self.logger.info('Searching for ethernet devices attached to vm...')
        for device in vm.config.hardware.device:
            # TODO: let user decide , which nic to change and default to first
            if isinstance(device, vim.vm.device.VirtualEthernetCard):
                # build object with change specifications
                nicspec = vim.vm.device.VirtualDeviceSpec()
                nicspec.operation = vim.vm.device.VirtualDeviceSpec.Operation.edit
                nicspec.device = device

                # locate network, which should be assigned to device
                network = self.get_obj([vim.dvs.DistributedVirtualPortgroup], net)
                if not network:
                    raise VmCLIException('Unable to find provided network {}'.format(net))

                dvs_port_conn = vim.dvs.PortConnection()
                # use portGroupKey and DVS switch to build connection object
                dvs_port_conn.portgroupKey = network.key
                dvs_port_conn.switchUuid = network.config.distributedVirtualSwitch.uuid

                # specify backing that connects device to a DVS switch portgroup
                nicspec.device.backing = vim.vm.device.VirtualEthernetCard.DistributedVirtualPortBackingInfo()
                nicspec.device.backing.port = dvs_port_conn
                # specify power status for nic
                nicspec.device.connectable = vim.vm.device.VirtualDevice.ConnectInfo()
                nicspec.device.connectable.connected = True
                nicspec.device.connectable.startConnected = True
                nicspec.device.connectable.allowGuestControl = True
                break

        # create object containing final configuration specification, which to apply
        if nicspec:
            config_spec = vim.vm.ConfigSpec(deviceChange=[nicspec])
            self.logger.info("Attaching network {} to VM's device {}...".format(net, dev))
            task = vm.ReconfigVM_Task(config_spec)
            self.worker.wait_for_tasks([task])
        else:
            raise VmCLIException('Unable to find any ethernet devices on a specified target!')


class ExecCommands(BaseCommands):
    """execute commands inside vm's guest operating system."""

    def __init__(self, *args, **kwargs):
        super(ExecCommands, self).__init__(*args, **kwargs)

    @args('--name', required=True, help='name of a object where to run command')
    @args('--guest-user', help="guest's user under which to run command")
    @args('--guest-pass', help="guest user's password")
    @args('--cmd', help="commands to execute e.g. --cmd ['cmd1', 'cmd2']", type=list)
    def execute(self, args):
        try:
            self.exec_inside_vm(args.name, args.cmd, args.guest_user, args.guest_pass, wait_for_tools=True)
        except VmCLIException as e:
            self.logger.error(e.message)
            sys.exit(4)

    def exec_inside_vm(self, name, commands, guest_user=None, guest_pass=None, wait_for_tools=False):
        """Runs provided command inside guest's operating system."""
        guest_user = guest_user or VM_GUEST_USER
        guest_pass = guest_pass or VM_GUEST_PASS
        vm = self.get_obj([VMWARE_TYPES['vm']], name)
        if not commands:
            raise VmCLIException('No command provided for execution!')

        self.logger.info("Checking if guest's OS has vmtools installed ...")
        if vm.guest.toolsStatus in ['toolsNotInstalled', 'toolsNotRunning'] and not wait_for_tools:
            raise VmCLIException("Guest's VMware tools are not installed or not running. Cannot continue")
        elif wait_for_tools:
            self.worker.wait_for_guest_vmtools(vm)

        try:
            credentials = vim.vm.guest.NamePasswordAuthentication(username=guest_user, password=guest_pass)
            for cmd in commands:
                executable = cmd.split()[0].lstrip()
                arguments = ' '.join(cmd.split()[1:])
                try:
                    self.logger.info('Running command "{} {}" inside guest'.format(executable, arguments))
                    progspec = vim.vm.guest.ProcessManager.ProgramSpec(programPath=executable, arguments=arguments)
                    self.content.guestOperationsManager.processManager.StartProgramInGuest(vm, credentials, progspec)
                except vim.fault.FileNotFound as e:
                    raise VmCLIException(e.msg + '. Try providing absolute path to the binary.')
        except vim.fault.InvalidGuestLogin as e:
            raise VmCLIException(e.msg)


class PowerCommands(BaseCommands):
    """run power action on a specific vm."""

    def __init__(self, *args, **kwargs):
        super(PowerCommands, self).__init__(*args, **kwargs)

    @args('--name', required=True, help='name of a managed object')
    @args('--on', help='power on vm', action='store_true')
    @args('--off', help='power off vm', action='store_true')
    @args('--reboot', help='reboot vm', action='store_true')
    @args('--reset', help='power reset vm', action='store_true')
    @args('--show', help='show power state of a vm', action='store_true')
    def execute(self, args):
        if args.on:
            self.poweron_vm(args.name)
        elif args.off:
            self.poweroff_vm(args.name)
        elif args.reboot:
            self.reboot_vm(args.name)
        elif args.reset:
            self.reset_vm(args.name)
        elif args.show:
            vm = self.get_obj([VMWARE_TYPES['vm']], args.name)
            print(vm.runtime.powerState)

    def poweron_vm(self, name):
        vm = self.get_obj([VMWARE_TYPES['vm']], name)
        if vm.runtime.powerState == 'poweredOff':
            self.worker.wait_for_tasks([vm.PowerOnVM_Task()])

    def poweroff_vm(self, name):
        vm = self.get_obj([VMWARE_TYPES['vm']], name)
        if vm.runtime.powerState == 'poweredOn':
            self.worker.wait_for_tasks([vm.PowerOffVM_Task()])

    def reboot_vm(self, name):
        vm = self.get_obj([VMWARE_TYPES['vm']], name)
        self.worker.wait_for_tasks([vm.RebootGuest()])

    def reset_vm(self, name):
        vm = self.get_obj([VMWARE_TYPES['vm']], name)
        self.worker.wait_for_tasks([vm.ResetVM_Task()])


# TODO: should the bundle fail, provide option to rerun from failed command e.g. ansibles site.retry
class CreateVmCommandBundle(BaseCommands):
    """execute series of tasks necessary to deploy new vm via cloning."""

    def __init__(self, *args, **kwargs):
        super(CreateVmCommandBundle, self).__init__(*args, **kwargs)

    @args('--name', required=True, help='name for a new vm')
    @args('--template', help='template object to use as a source of cloning')
    @args('--flavor', help='flavor to use for a vm cloning')
    @args('--datacenter', help='datacenter where to create vm')
    @args('--folder', help='folder where to place vm')
    @args('--datastore', help='datastore where to store vm')
    @args('--cluster', help='cluster where to spawn mv')
    @args('--resource-pool', help='resource pool, which should be used for vm')
    @args('--mem', help='memory to set for a vm in megabytes', type=int)
    @args('--cpu', help='cpu count to set for a vm', type=int)
    @args('--hdd', help='size of additional hdd to attach in gigabytes', type=int)
    @args('--net', help='network to attach to the vm')
    @args('--net-cfg', help="network configuration. E.g --net-cfg '10.1.10.2/24'")
    @args('--guest-user', help="guest's user under which to run command")
    @args('--guest-pass', help="guest user's password")
    def execute(self, args):
        flavor = load_vm_flavor(args.flavor)

        # load needed variables
        name = args.name
        template = args.template or flavor.get('template', None) or VM_TEMPLATE
        datacenter = args.datacenter or flavor.get('datacenter', None) or VM_DATACENTER
        folder = args.folder or flavor.get('folder', None) or VM_FOLDER
        datastore = args.datastore or flavor.get('datastore', None) or VM_DATASTORE
        cluster = args.cluster or flavor.get('cluster', None) or VM_CLUSTER
        resource_pool = args.resource_pool or flavor.get('resource_pool', None) or VM_RESOURCE_POOL
        mem = args.mem or flavor.get('mem', None) or VM_MEM
        cpu = args.cpu or flavor.get('cpu', None) or VM_CPU
        hdd = args.hdd or flavor.get('hdd', None) or VM_HDD
        net = args.net or flavor.get('net', None) or VM_NETWORK
        net_cfg = args.net_cfg or flavor.get('net_cfg', None) or VM_NETWORK_CFG
        guest_user = args.guest_user or VM_GUEST_USER
        guest_pass = args.guest_pass or VM_GUEST_PASS

        if not name or not template:
            raise VmCLIException('Arguments name or template are missing, cannot continue!')

        # Initialize used commands
        clone = CloneCommands()
        modify = ModifyCommands()
        power = PowerCommands()
        attach = AttachCommands()
        execute = ExecCommands()

        # Clone virtual machine and leave it powered off
        clone.clone_vm(name, template, datacenter, folder, datastore, cluster, resource_pool, poweron=False)
        # If any, apply hardware changes to the virtual machine
        if mem or cpu:
            modify.change_hw_resource(name, mem, cpu)
        if net:
            # TODO: dev is ignored at the moment, but there will be eth0 in the future
            modify.change_network(name, net, dev=None)
        if hdd:
            attach.attach_hdd(name, hdd)
        # Power on freshly cloned virtual machine
        power.poweron_vm(name)
        # Wait for guest OS to boot up
        self.worker.wait_for_guest_os(self.get_obj([VMWARE_TYPES['vm']], name))

        # Configure first ethernet device on the host, assumes traditional naming scheme
        if net_cfg:
            try:
                ip = netaddr.IPNetwork(net_cfg)
                gateway = list(ip)[1]
                ip_addr = str(ip)
            except netaddr.core.AddrFormatError as e:
                ip, gateway = None, None
                self.logger.warning(str(e.message) + '. Skipping network configuration')

            if ip and gateway:
                commands = [
                    '/bin/ip addr flush dev eth0',
                    '/bin/ip addr add {} brd + dev eth0'.format(ip_addr),
                    '/bin/ip route add default via {}'.format(gateway)
                ]
                if VM_ADDITIONAL_CMDS:
                    commands.extend(VM_ADDITIONAL_CMDS)

                execute.exec_inside_vm(name, commands, guest_user, guest_pass, wait_for_tools=True)

        self.logger.info('Deployed vm {} {}'.format(name, ip.ip))


def get_arg_subparsers(parser):
    """Iterates over function's or method's __dict__['args'] variable to load arguments into arg parser."""
    subparsers = parser.add_subparsers(help='sub-command help', dest='subcommand')
    for command in COMMANDS:
        obj = COMMANDS[command]()
        # use docstring as a help and define subcommand in argument parser
        desc = getattr(obj, '__doc__', None)
        sub_parser = subparsers.add_parser(command, help=desc)

        # get all class public methods
        command_methods = [getattr(obj, m) for m in dir(obj) if callable(getattr(obj, m)) and not m.startswith('_')]
        # iterate over callable methods and load defined arguments
        arguments = dict()
        for method in command_methods:
            for args, kwargs in getattr(method, 'args', []):
                # if argument does not have 'dest' parameter, it's name will be used instead
                dest = kwargs.get('dest', None) or args[0].lstrip('-')
                if dest not in arguments:
                    sub_parser.add_argument(*args, **kwargs)
                # make sure only first argument is used if two or more are found with the same name
                arguments.setdefault(dest, [args, kwargs])

    return parser


# Register commands to be available to user, key will be used as a subcommand name:
# ./vmcli.py list ...
COMMANDS = OrderedDict([
    ('list', ListCommands),
    ('clone', CloneCommands),
    ('create', CreateVmCommandBundle),
    ('create-empty', CreateEmptyVmCommands),
    ('attach', AttachCommands),
    ('modify', ModifyCommands),
    ('exec', ExecCommands),
    ('power', PowerCommands),
])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Command line utility to interact with VMware vSphere API')
    parser.add_argument('--log-level', help='set log level', choices=LOG_LEVEL_CHOICES)
    parser.add_argument('-q', '--quiet', help='quiet mode, no messages are shown', action='store_true')
    parser.add_argument('-u', '--username', help='login name to use for vcenter', default=None)
    parser.add_argument('-p', '--password', help='password for specified login', default=None)
    parser.add_argument('-s', '--vcenter', help='name of vcenter, which to connect to', default=None)
    parser.add_argument('-i', '--insecure', help='skip SSL verification', action='store_true')
    # Load in options from Command classes
    parser = get_arg_subparsers(parser)
    args = parser.parse_args()

    if args.log_level:
        logger.setLevel(args.log_level)
    if args.quiet:
        logger.quiet()

    connect(args.vcenter, args.username, args.password, args.insecure)

    # load appropiate command, argparse will handle correct input for us
    command = COMMANDS[args.subcommand]()
    try:
        command.execute(args)
    except VmCLIException as e:
        logger.critical(e.message)
        sys.exit(1)
