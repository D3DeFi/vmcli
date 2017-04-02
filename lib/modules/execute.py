from pyVmomi import vim

from lib.modules import BaseCommands
from lib.tools.argparser import args
from lib.exceptions import VmCLIException


class ExecCommands(BaseCommands):
    """execute commands inside vm's guest operating system."""

    def __init__(self, *args, **kwargs):
        super(ExecCommands, self).__init__(*args, **kwargs)

    @args('--name', required=True, help='name of a object where to run command')
    @args('--guest-user', help="guest's user under which to run command", map='VM_GUEST_USER')
    @args('--guest-pass', help="guest user's password", map='VM_GUEST_PASS')
    @args('--cmd', help="commands to execute e.g. --cmd 'cmd1; cmd2'", type=str)
    def execute(self, args):
        try:
            # When this method is executed, command was called directly from cmd line and content of cmd argument,
            # separated by semicolon, needs to be converted into list
            args.cmd = args.cmd.split(';')
            self.exec_inside_vm(args.name, args.cmd, args.guest_user, args.guest_pass, wait_for_tools=False)
        except VmCLIException as e:
            self.exit(e.message, errno=4)

    def exec_inside_vm(self, name, commands, guest_user=None, guest_pass=None, wait_for_tools=False):
        """Runs provided command inside guest's operating system."""
        self.logger.info('Loading required VMware resources...')
        vm = self.get_obj('vm', name)
        if not commands:
            raise VmCLIException('No command provided for execution!')

        self.logger.info("Checking if guest's OS has vmtools installed ...")
        if wait_for_tools:
            self.wait_for_guest_vmtools(vm)

        if vm.guest.toolsStatus in ['toolsNotInstalled', 'toolsNotRunning']:
            raise VmCLIException("Guest's VMware tools are not installed or not running. Aborting...")

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


BaseCommands.register('exec', ExecCommands)
