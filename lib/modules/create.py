import netaddr
from pyVmomi import vim

from lib.modules import BaseCommands
from lib.tools import normalize_memory
from lib.tools.argparser import args
from lib.exceptions import VmCLIException
from flavors import load_vm_flavor

import lib.config as conf
import lib.constants as c

# import commands to be used in bundles
from lib.modules.clone import CloneCommands
from lib.modules.modify import ModifyCommands
from lib.modules.power import PowerCommands
from lib.modules.attach import AttachCommands
from lib.modules.execute import ExecCommands


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
        folder = args.folder or flavor.get('folder', None) or conf.VM_FOLDER
        resource_pool = args.resource_pool or flavor.get('resource_pool', None) or conf.VM_RESOURCE_POOL
        # Add datastore-cluster support to create-empty operation
        datastore = args.datastore or flavor.get('datastore', None) or conf.VM_DATASTORE
        mem = args.mem or flavor.get('mem', None) or conf.VM_MEM
        cpu = args.cpu or flavor.get('cpu', None) or conf.VM_CPU

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
            mem = c.VM_MIN_MEM
        mem = normalize_memory(mem)

        if not cpu:
            cpu = c.VM_MIN_CPU
        elif cpu < c.VM_MIN_CPU or cpu > c.VM_MAX_CPU:
            raise VmCLIException('CPU count must be between {}-{}'.format(c.VM_MIN_CPU, c.VM_MAX_CPU))

        # configuration specification for the new vm, if no mem and cpu is provided, minimal values will be used
        config_spec = vim.vm.ConfigSpec()
        config_spec.name = name
        config_spec.memoryMB = mem
        config_spec.numCPUs = cpu
        config_spec.files = vm_files
        config_spec.guestId = 'otherLinux64Guest'
        config_spec.version = 'vmx-08'

        folder = self.get_obj('folder', folder)
        resource_pool = self.get_obj('resource_pool', resource_pool)
        task = folder.CreateVM_Task(config=config_spec, pool=resource_pool)
        self.wait_for_tasks([task])


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
    @args('--mem', help='memory to set for a vm in megabytes')
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
        # TODO: Some of this is duplicitly checked in clone_vm too
        template = args.template or flavor.get('template', None) or conf.VM_TEMPLATE
        datacenter = args.datacenter or flavor.get('datacenter', None) or conf.VM_DATACENTER
        folder = args.folder or flavor.get('folder', None) or conf.VM_FOLDER
        datastore = args.datastore or flavor.get('datastore', None) or conf.VM_DATASTORE
        cluster = args.cluster or flavor.get('cluster', None) or conf.VM_CLUSTER
        resource_pool = args.resource_pool or flavor.get('resource_pool', None) or conf.VM_RESOURCE_POOL
        mem = args.mem or flavor.get('mem', None) or conf.VM_MEM
        cpu = args.cpu or flavor.get('cpu', None) or conf.VM_CPU
        hdd = args.hdd or flavor.get('hdd', None) or conf.VM_HDD
        net = args.net or flavor.get('net', None) or conf.VM_NETWORK
        net_cfg = args.net_cfg or flavor.get('net_cfg', None) or conf.VM_NETWORK_CFG
        guest_user = args.guest_user or conf.VM_GUEST_USER
        guest_pass = args.guest_pass or conf.VM_GUEST_PASS

        if not name or not template:
            raise VmCLIException('Arguments name or template are missing, cannot continue!')

        # Initialize used commands
        clone = CloneCommands(self.connection)
        modify = ModifyCommands(self.connection)
        power = PowerCommands(self.connection)
        attach = AttachCommands(self.connection)
        execute = ExecCommands(self.connection)

        clone.clone_vm(name, template, datacenter, folder, datastore, cluster, resource_pool, False, mem, cpu)

        if net:
            # Change network assigned to the first interface on the VM
            modify.change_network(name, net, dev=1)
        if hdd:
            attach.attach_hdd(name, hdd)

        power.poweron_vm(name)
        self.wait_for_guest_os(self.get_obj('vm', name))

        # Configure first ethernet device on the host, assumes traditional naming scheme
        if net_cfg:
            # assume prefix 24 if user forgots
            if len(net_cfg.split('/')) == 1:
                net_cfg += '/24'

            try:
                ip = netaddr.IPNetwork(net_cfg)
                gateway = list(ip)[1]
                ip_addr = str(ip)
            except netaddr.core.AddrFormatError as e:
                ip, gateway = None, None
                self.logger.warning(str(e.message) + '. Skipping network configuration')

            if ip and gateway:
                # ugly hack assuming templates should have just one interface. Only work for Debian at the moment
                commands = [
                    '/bin/cp /etc/network/interfaces /etc/network/interfaces.bak',
                    "/bin/sed -i 's/allow-hotplug/auto/' /etc/network/interfaces",
                    "/bin/sed -i 's/address .*/address {}/' /etc/network/interfaces".format(ip.ip),
                    "/bin/sed -i 's/netmask .*/netmask {}/' /etc/network/interfaces".format(ip.netmask),
                    "/bin/sed -i 's/network .*/network {}/' /etc/network/interfaces".format(ip.network),
                    "/bin/sed -i 's/gateway .*/gateway {}/' /etc/network/interfaces".format(gateway),
                    "/bin/sed -i 's/broadcast .*/broadcast {}/' /etc/network/interfaces".format(ip.broadcast),
                    '/sbin/ifdown -a && /bin/sleep 1 && /sbin/ifup -a'
                ]
                execute.exec_inside_vm(name, commands, guest_user, guest_pass, wait_for_tools=True)

        if conf.VM_ADDITIONAL_CMDS:
            execute.exec_inside_vm(name, conf.VM_ADDITIONAL_CMDS, guest_user, guest_pass, wait_for_tools=True)

        self.logger.info('Deployed vm {}'.format(name))


BaseCommands.register('create', CreateVmCommandBundle)
BaseCommands.register('create-empty', CreateEmptyVmCommands)
