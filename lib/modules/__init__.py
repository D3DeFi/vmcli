import os
import sys
import time
from collections import OrderedDict
from importlib import import_module
from pyVmomi import vim, vmodl

from lib.tools.logger import logger
from lib.exceptions import VmCLIException

from lib.config import VM_OS_TIMEOUT, VM_TOOLS_TIMEOUT
from lib.constants import VMWARE_TYPES


# Object containing registered subcommands to be available to user. Dictionary is used in command line argument
# parsing of arguments defined with @args decorator as well as subcommand execution.
# Key will be used as a subcommand name, e.g.: ./vmcli.py list ...
COMMANDS = OrderedDict()


def module_loader(file_name):
    """According to the listing output of the modules directory, method iterates over files located in the directory
    and loads appropiate subcommands, if name of the file being processed does not starts with underscore."""
    base_dir = os.path.dirname(os.path.dirname(file_name))
    modules_dir = os.path.join(base_dir, 'lib/modules/')
    modules_dir = os.listdir(modules_dir)
    # registered subcomands will be added into COMMANDS dictionary upon import
    for module in modules_dir:
        # do not process __init__.py file and everything else not ending with .py
        if not module.startswith('_') and module.endswith('.py'):
            # remove .py extensions
            module = module[:-3]
            import_module('lib.modules.{}'.format(module))

    return COMMANDS


class BaseCommands(object):
    """Introduces base class for other Commands classes with sharing of same connection content
    and object retrieval. Should be subclassed and its method execute() overriden. Docstring of the
    BaseCommands class should be overriden as well, beacause it will be used as a help for subcommand."""

    def __init__(self, connection=None):
        self.logger = logger
        self.connection = connection
        if connection:
            self.content = connection.RetrieveContent()
        else:
            self.content = None

    def execute(self, args):
        """Routes to a correct method based on arguments provided. This is also the perfect place
        to define generic arguments, which should be used for every method, via args decorator."""
        raise NotImplementedError("Cannot call super's execute() method! This method must be overidden.")

    def get_obj(self, vimtype, name, default=False):
        """Gets the vsphere object associated with a given text name.
        If default is set to True and name does not match, return first object found."""
        vimtype = VMWARE_TYPES.get(vimtype, None)
        if not vimtype:
            raise VmCLIException('Provided type does not match any existing VMware object types!')

        # TODO: make cache or find better way to retreive objects + destroy view object (it is huge in mem)
        # Create container view containing object found
        container = self.content.viewManager.CreateContainerView(self.content.rootFolder, [vimtype], True)
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

    @staticmethod
    def register(name, class_name):
        """Registers class itself as a subcommand with a provided name."""
        global COMMANDS
        if COMMANDS.get(name, None):
            raise VmCLIException('Subcommand with the name {} already registered!'.format(name))
        else:
            COMMANDS[name] = class_name

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

    def wait_for_tasks(self, tasks):
        """Method waits for all of the provided tasks and returns after they finished their runs."""
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

    def exit(self, msg, errno=1):
        """Provides way to fail during execution."""
        self.logger.error(msg)
        try:
            int(errno)
            sys.exit(errno)
        except ValueError:
            sys.exit(1)
