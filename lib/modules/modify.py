from pyVmomi import vim

from lib.modules import BaseCommands
from lib.tools import normalize_memory
from lib.tools.argparser import args
from lib.exceptions import VmCLIException

import lib.constants as c


class ModifyCommands(BaseCommands):
    """modify VMware objects resources or configuration."""

    def __init__(self, *args, **kwargs):
        super(ModifyCommands, self).__init__(*args, **kwargs)

    @args('--name', required=True, help='name of a object to modify')
    def execute(self, args):
        if args.mem or args.cpu:
            self.change_hw_resource(args.name, args.mem, args.cpu)
        elif args.net:
            self.change_network(args.name, args.net, args.dev)
        elif args.vHWversion:
            self.change_vHWversion(args.name, args.vHWversion)
        else:
            raise VmCLIException('Too few arguments. Aborting...')

    @args('--mem', help='memory to set for a vm in megabytes')
    @args('--cpu', help='cpu count to set for a vm', type=int)
    def change_hw_resource(self, name, mem=None, cpu=None):
        """Changes hardware resource of a specific VM."""
        if not mem and not cpu:
            raise VmCLIException('Neither memory or cpu specified! Cannot run hardware reconfiguration.')

        vm = self.get_vm_obj(name, fail_missing=True)
        config_spec = vim.vm.ConfigSpec()
        if mem:
            mem = normalize_memory(mem)
            self.logger.info("Increasing memory to {} megabytes...".format(mem))
            config_spec.memoryMB = mem

        if cpu:
            if cpu < c.VM_MIN_CPU or cpu > c.VM_MAX_CPU:
                raise VmCLIException('CPU count must be between {}-{}'.format(c.VM_MIN_CPU, c.VM_MAX_CPU))
            else:
                self.logger.info("Increasing cpu count to {} cores...".format(cpu))
                config_spec.numCPUs = cpu

        task = vm.ReconfigVM_Task(config_spec)
        self.wait_for_tasks([task])

    @args('--net', help='network to attach to a network device')
    @args('--dev', type=int, default=1, help='serial number of device to modify (e.g. 1 == eth0, 2 == eth1)')
    def change_network(self, name, net, dev):
        """Changes network associated with a specifc VM's network interface."""
        vm = self.get_vm_obj(name, fail_missing=True)
        # locate network, which should be assigned to device
        network = self.get_obj('network', net)
        if not network:
            raise VmCLIException('Unable to find provided network {}! Aborting...'.format(net))

        # search for Ethernet devices
        self.logger.info('Searching for ethernet devices attached to vm...')
        nic_counter = 1
        for device in vm.config.hardware.device:
            # Search for a specific network interfaces
            if isinstance(device, vim.vm.device.VirtualEthernetCard):
                if nic_counter != dev:
                    nic_counter += 1
                    continue

                if isinstance(network, vim.dvs.DistributedVirtualPortgroup):
                    # specify backing that connects device to a DVS switch portgroup
                    dvs_port_conn = vim.dvs.PortConnection(
                            portgroupKey=network.key, switchUuid=network.config.distributedVirtualSwitch.uuid)
                    backing = vim.vm.device.VirtualEthernetCard.DistributedVirtualPortBackingInfo(port=dvs_port_conn)
                else:
                    # expect simple vim.Network if DistributedVirtualPortgroup was not used
                    backing = vim.vm.device.VirtualEthernetCard.NetworkBackingInfo(
                        useAutoDetect=False, network=network, deviceName=net)

                device.backing = backing
                # specify power status for nic
                device.connectable = vim.vm.device.VirtualDevice.ConnectInfo(
                        connected=True, startConnected=True, allowGuestControl=True)

                # build object with change specifications
                nicspec = vim.vm.device.VirtualDeviceSpec(device=device)
                nicspec.operation = vim.vm.device.VirtualDeviceSpec.Operation.edit

                config_spec = vim.vm.ConfigSpec(deviceChange=[nicspec])
                self.logger.info("Attaching network {} to {}. network device on VM...".format(net, dev))
                task = vm.ReconfigVM_Task(config_spec)
                self.wait_for_tasks([task])
                return

        raise VmCLIException('Unable to find ethernet device on a specified target!')

    @args('--vHWversion', help='VM hardware version number to assign to the VM or \'latest\'', metavar='VER')
    def change_vHWversion(self, name, vHWversion=None):
        """Changes VM HW version. If version is None, then VM is set to the latest version."""
        vm = self.get_vm_obj(name, fail_missing=True)
        if vHWversion == 'latest':
            version = None      # None will default to latest so we don't need to search for it
        else:
            try:
                version = 'vmx-{:02d}'.format(vHWversion)
            except ValueError:
                raise VmCLIException('VM version must be integer or \'latest\'! Aborting...')

        if vm.runtime.powerState != 'poweredOff':
            raise VmCLIException('VM hardware version change cannot be performed on running VM! Aborting...')

        self.logger.info('Updating VM hardware version...')
        try:
            task = vm.UpgradeVM_Task(version=version)
            self.wait_for_tasks([task])
        except vim.fault.AlreadyUpgraded:
            pass


BaseCommands.register('modify', ModifyCommands)
