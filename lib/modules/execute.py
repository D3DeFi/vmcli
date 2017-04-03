import os
import json
import subprocess

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

    def exec_callbacks(self, args, callback_args):
        """Runs any executable present inside project/callbacks/ directory on host with provided arguments.
        First argument to executable is always JSON object containing all arguments passed to vmcli and its
        subcommands via cli. Following are arguments passed as a value via command line argument callback.
        For example, this --callback 'var1; var2; multi word var' will be passed as:
        ./callbacks/script.sh '{"name": "..", "template": ...}' 'var1' 'var2' 'multi word var'
        """
        # Parse additional callback arguments passed from command line
        callback_args = [x.lstrip() for x in callback_args.rstrip(';').split(';')]
        # Get all callback scripts
        callbacks_dir = sorted(os.listdir('callbacks/'))
        callbacks = [os.path.realpath('callbacks/' + x) for x in callbacks_dir if not x.startswith('.')]
        # Prepare JSON serializable object from args namespace
        arguments = {}
        for argument in [x for x in dir(args) if not x.startswith('_')]:
            arguments[argument] = getattr(args, argument, None)
        arguments = json.dumps(arguments)

        for executable in callbacks:
            self.logger.info('Running callback "{}" ...'.format(executable))
            command = [executable, arguments]
            command.extend(callback_args)
            try:
                subprocess.Popen(command).communicate()
            except OSError:
                raise VmCLIException('Unable to execute callback {}! Check it for errors'.format(executable))


BaseCommands.register('exec', ExecCommands)
