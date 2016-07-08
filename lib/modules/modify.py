from pyVmomi import vim

from lib.modules import BaseCommands
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
            try:
                self.change_hw_resource(args.name, args.mem, args.cpu)
            except VmCLIException as e:
                self.exit(e.message, errno=3)
        elif args.net and args.dev:
            self.change_network(args.name, args.net, args.dev)

    @args('--mem', help='memory to set for a vm in megabytes', type=int)
    @args('--cpu', help='cpu count to set for a vm', type=int)
    def change_hw_resource(self, name, mem=None, cpu=None):
        """Changes hardware resource of a specific VM."""
        vm = self.get_obj('vm', name)
        if not mem and not cpu:
            raise VmCLIException('Neither memory or cpu specified! Cannot run hardware reconfiguration.')

        config_spec = vim.vm.ConfigSpec()
        if mem:
            # TODO: allow to pass --mem 512M or --mem 1G
            if mem < c.VM_MIN_MEM or mem > c.VM_MAX_MEM:
                raise VmCLIException('Memory must be between {}-{}'.format(c.VM_MIN_MEM, c.VM_MAX_MEM))
            else:
                config_spec.memoryMB = mem

        if cpu:
            if cpu < c.VM_MIN_CPU or cpu > c.VM_MAX_CPU:
                raise VmCLIException('CPU count must be between {}-{}'.format(c.VM_MIN_CPU, c.VM_MAX_CPU))
            else:
                config_spec.numCPUs = cpu

        self.logger.info("Setting vm's resources according to specification...")
        task = vm.ReconfigVM_Task(config_spec)
        self.wait_for_tasks([task])

    @args('--net', help='network to attach to a network device')
    @args('--dev', help='device to attach provided network to')
    def change_network(self, name, net, dev):
        """Changes network associated with a specifc VM's network interface."""
        vm = self.get_obj('vm', name)
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
                network = self.get_obj('dvs_portgroup', net)
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
            self.wait_for_tasks([task])
        else:
            raise VmCLIException('Unable to find any ethernet devices on a specified target!')


BaseCommands.register('modify', ModifyCommands)
