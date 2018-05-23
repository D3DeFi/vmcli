from pyVmomi import vim

from lib.modules import BaseCommands
from lib.tools.argparser import args
from lib.exceptions import VmCLIException

import lib.config as conf
from lib.constants import VM_MIN_HDD, VM_MAX_HDD


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
            self.exit(e.message, errno=5)

    @args('--size', help='size of a disk to attach in gigabytes (hdd only)', type=int)
    def attach_hdd(self, name, size):
        """Attaches disk to a virtual machine. If no SCSI controller is present, then it is attached as well."""
        if not size or size < VM_MIN_HDD or size > VM_MAX_HDD:
            raise VmCLIException('Hdd size must be between {}-{}'.format(VM_MIN_HDD, VM_MAX_HDD))

        vm = self.get_obj('vm', name)

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
        self.wait_for_tasks([task])

    @args('--net', help='net to attach to a new device (network only)')
    def attach_net_adapter(self, name, net):
        """Attaches virtual network adapter to the vm associated with a VLAN passed via argument."""
        self.logger.info('Loading required VMware resources...')
        vm = self.get_obj('vm', name)
        if not vm:
            raise VmCLIException('Unable to find specified VM {}! Aborting...'.format(name))
        # locate network, which should be assigned to device
        network = self.get_obj('network', net)
        if not network:
            raise VmCLIException('Unable to find provided network {}! Aborting...'.format(net))

        # build virtual device
        device = vim.vm.device.VirtualVmxnet3(deviceInfo=vim.Description())

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
               connected=False, startConnected=True, allowGuestControl=True)

        # build object with change specifications
        nicspec = vim.vm.device.VirtualDeviceSpec(device=device)
        nicspec.operation = vim.vm.device.VirtualDeviceSpec.Operation.add

        config_spec = vim.vm.ConfigSpec(deviceChange=[nicspec])
        self.logger.info('Attaching network device to the virtual machine {}...'.format(name))
        task = vm.ReconfigVM_Task(config_spec)
        self.wait_for_tasks([task])

    def attach_floppy_drive(self, name):
        """Attaches floppy drive to the virtual machine."""
        vm = self.get_obj('vm', name)
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
        self.wait_for_tasks([task])

    def attach_cdrom_drive(self, name):
        """Attaches cd/dvd drive to the virtual machine."""
        vm = self.get_obj('vm', name)
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
        self.wait_for_tasks([task])


BaseCommands.register('attach', AttachCommands)
