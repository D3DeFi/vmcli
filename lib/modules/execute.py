import sys
from pyVmomi import vim

from lib.modules import BaseCommands
from lib.tools.argparser import args
from lib.exceptions import VmCLIException

import lib.config as conf
from lib.constants import VMWARE_TYPES


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
        guest_user = guest_user or conf.VM_GUEST_USER
        guest_pass = guest_pass or conf.VM_GUEST_PASS
        vm = self.get_obj([VMWARE_TYPES['vm']], name)
        if not commands:
            raise VmCLIException('No command provided for execution!')

        self.logger.info("Checking if guest's OS has vmtools installed ...")
        if vm.guest.toolsStatus in ['toolsNotInstalled', 'toolsNotRunning'] and not wait_for_tools:
            raise VmCLIException("Guest's VMware tools are not installed or not running. Cannot continue")
        elif wait_for_tools:
            self.wait_for_guest_vmtools(vm)

        try:
            credentials = vim.vm.guest.NamePasswordAuthentication(username=guest_user, password=guest_pass)
            # TODO: make commands same way as VM_ADDITIONAL_CMDS from config file (delimited by ;)
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
