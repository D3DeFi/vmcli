import netaddr
from pyVmomi import vim

from lib.modules import BaseCommands
from lib.tools import normalize_memory
from lib.tools.argparser import args
from lib.exceptions import VmCLIException

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
    @args('--folder', help='folder where to place vm', map='VM_FOLDER')
    @args('--resource-pool', help='resource pool, which should be used for vm', map='VM_RESOURCE_POOL')
    @args('--datastore', help='datastore where to store vm', map='VM_DATASTORE')
    @args('--mem', help='memory to set for a vm in megabytes', map='VM_MEM')
    @args('--cpu', help='cpu count to set for a vm', type=int, map='VM_CPU')
    def execute(self, args):
        """Creates empty vm without disk."""
        if not (args.name or args.folder or args.resource_pool or args.datastore):
            raise VmCLIException('Missing arguments! Make sure name, folder, resource_pool and datastore are present.')

        # Store logs and snapshots withing same directory as ds_path, which is [datastore]vm_name
        ds_path = '[{}]{}'.format(args.datastore, args.name)
        vm_files = vim.vm.FileInfo(logDirectory=None, snapshotDirectory=None, suspendDirectory=None, vmPathName=ds_path)
        # Load cpu and memory configuration
        if not args.mem:
            args.mem = c.VM_MIN_MEM
        args.mem = normalize_memory(args.mem)

        if not args.cpu:
            args.cpu = c.VM_MIN_CPU
        elif args.cpu < c.VM_MIN_CPU or args.cpu > c.VM_MAX_CPU:
            raise VmCLIException('CPU count must be between {}-{}'.format(c.VM_MIN_CPU, c.VM_MAX_CPU))

        # configuration specification for the new vm, if no mem and cpu is provided, minimal values will be used
        config_spec = vim.vm.ConfigSpec()
        config_spec.name = args.name
        config_spec.memoryMB = args.mem
        config_spec.numCPUs = args.cpu
        config_spec.files = vm_files
        config_spec.guestId = 'otherLinux64Guest'

        folder = self.get_obj('folder', args.folder)
        resource_pool = self.get_obj('resource_pool', args.resource_pool)
        task = folder.CreateVM_Task(config=config_spec, pool=resource_pool)
        self.wait_for_tasks([task])


# TODO: should the bundle fail, provide option to rerun from failed command e.g. ansibles site.retry
class CreateVmCommandBundle(BaseCommands):
    """execute series of tasks necessary to deploy new vm via cloning."""

    def __init__(self, *args, **kwargs):
        super(CreateVmCommandBundle, self).__init__(*args, **kwargs)

    @args('--name', required=True, help='name for a new vm')
    @args('--template', '--tem', help='template object to use as a source of cloning', map='VM_TEMPLATE')
    @args('--flavor', help='flavor to use for a vm cloning')
    @args('--datacenter', '--dc', help='datacenter where to create vm', map='VM_DATACENTER')
    @args('--folder', help='folder where to place vm', map='VM_FOLDER')
    @args('--datastore', '--ds', help='datastore where to store vm', map='VM_DATASTORE')
    @args('--cluster', '--cl', help='cluster where to spawn mv', map='VM_CLUSTER')
    @args('--resource-pool', '--rpool', help='resource pool, which should be used for vm', map='VM_RESOURCE_POOL')
    @args('--mem', help='memory to set for a vm in megabytes', map='VM_MEM')
    @args('--cpu', help='cpu count to set for a vm', type=int, map='VM_CPU')
    @args('--hdd', help='size of additional hdd to attach in gigabytes', type=int, map='VM_HDD')
    @args('--net', help='network to attach to the vm', map='VM_NETWORK')
    @args('--net-cfg', help="network configuration. E.g --net-cfg '10.1.10.2/24'", map='VM_NETWORK_CFG')
    @args('--guest-user', '--gu', help="guest's user under which to run command through vmtools", map='VM_GUEST_USER')
    @args('--guest-pass', '--gp', help="guest user's password", map='VM_GUEST_PASS')
    @args('--callback', help='arguments to pass to callback functions. E.g. --callback "var1; var 2"')
    def execute(self, args):
        """Clones VM, assigns it proper hardware devices, powers it on ad prepares it for further configuration."""
        if not args.name or not args.template:
            raise VmCLIException('Arguments name or template are missing, cannot continue!')

        clone = CloneCommands(self.connection)
        clone.clone_vm(args.name, args.template, args.datacenter, args.folder, args.datastore,
                       args.cluster, args.resource_pool, False, args.mem, args.cpu, flavor=args.flavor)

        modify = ModifyCommands(self.connection)
        # Upgrade VM hardware version to the latest
        modify.change_vHWversion(args.name, vHWversion='latest')
        # Change network assigned to the first interface on the VM
        if args.net:
            modify.change_network(args.name, args.net, dev=1)
        if args.hdd:
            # Attach additional hard drive
            attach = AttachCommands(self.connection)
            attach.attach_hdd(args.name, args.hdd)

        power = PowerCommands(self.connection)
        power.poweron_vm(args.name)
        self.wait_for_guest_os(self.get_obj('vm', args.name))

        execute = ExecCommands(self.connection)
        # Configure first ethernet device on the host, assumes traditional naming scheme
        if args.net_cfg:
            # assume prefix 24 if user forgots
            if len(args.net_cfg.split('/')) == 1:
                args.net_cfg += '/24'

            try:
                ip = netaddr.IPNetwork(args.net_cfg)
                gateway = list(ip)[1]
            except netaddr.core.AddrFormatError as e:
                ip, gateway = None, None
                self.logger.warning(str(e.message) + '. Skipping network configuration')

            if ip and gateway:
                # expects script inside template
                commands = [
                    '/bin/bash /usr/share/vmcli/provision-interfaces.sh {} {} {} {} {}'.format(
                            ip.ip, ip.netmask, gateway, ip.network, ip.broadcast)
                ]
                execute.exec_inside_vm(args.name, commands, args.guest_user, args.guest_pass, wait_for_tools=True)

        if conf.VM_ADDITIONAL_CMDS:
            execute.exec_inside_vm(args.name, conf.VM_ADDITIONAL_CMDS, args.guest_user,
                                   args.guest_pass, wait_for_tools=True)

        self.logger.info('Deployed vm {}'.format(args.name))

        # Execute callbacks from callbacks/ directory
        if args.callback:
            execute.exec_callbacks(args, args.callback)


BaseCommands.register('create', CreateVmCommandBundle)
BaseCommands.register('create-empty', CreateEmptyVmCommands)
