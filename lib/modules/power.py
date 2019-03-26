from lib.modules import BaseCommands
from lib.tools.argparser import args


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
            vm = self.get_obj('vm', args.name)
            print(vm.runtime.powerState)

    def poweron_vm(self, name):
        vm = self.get_vm_obj(name, fail_missing=True)
        if vm.runtime.powerState == 'poweredOff':
            self.wait_for_tasks([vm.PowerOnVM_Task()])

    def poweroff_vm(self, name):
        vm = self.get_vm_obj(name, fail_missing=True)
        if vm.runtime.powerState == 'poweredOn':
            self.wait_for_tasks([vm.PowerOffVM_Task()])

    def reboot_vm(self, name):
        vm = self.get_vm_obj(name, fail_missing=True)
        self.wait_for_tasks([vm.RebootGuest()])

    def reset_vm(self, name):
        vm = self.get_vm_obj(name, fail_missing=True)
        self.wait_for_tasks([vm.ResetVM_Task()])


BaseCommands.register('power', PowerCommands)
