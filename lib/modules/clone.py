import sys
from pyVmomi import vim

from lib.modules import BaseCommands
from lib.tools.argparser import args
from lib.exceptions import VmCLIException

import lib.config as conf


class CloneCommands(BaseCommands):
    """clone specific VMware objects, without any further configuration."""

    def __init__(self, *args, **kwargs):
        super(CloneCommands, self).__init__(*args, **kwargs)

    @args('--name', required=True, help='name for a cloned object')
    @args('--template', required=True, help='template object to use as a source of cloning')
    def execute(self, args):
        try:
            self.clone_vm(args.name, args.template, args.datacenter, args.folder,
                    args.datastore, args.cluster, args.resource_pool, args.poweron)
        except VmCLIException as e:
            self.logger.error(e.message)
            sys.exit(2)

    @args('--datacenter', help='datacenter where to create vm')
    @args('--folder', help='folder where to place vm')
    @args('--datastore', help='datastore where to store vm')
    @args('--cluster', help='cluster where to spawn mv')
    @args('--resource-pool', help='resource pool, which should be used for vm')
    @args('--poweron', help='whether to power on vm after cloning', action='store_true')
    def clone_vm(self, name, template, datacenter=None, folder=None, datastore=None,
                cluster=None, resource_pool=None, poweron=None):
        """Clones new virtual machine from a template or existing VM."""
        self.logger.info('Running cloning operation...')
        # load provided values or fill them with defaults
        template = template or conf.VM_TEMPLATE
        datacenter = datacenter or conf.VM_DATACENTER
        cluster = cluster or conf.VM_CLUSTER
        folder = folder or conf.VM_FOLDER
        datastore = datastore or conf.VM_DATASTORE
        resource_pool = resource_pool or conf.VM_RESOURCE_POOL
        if poweron is not False:
            poweron = poweron or conf.VM_POWERON
        # Access objects associated with the provided names
        try:
            vm = None
            vm = self.get_obj('vm', name)
        except VmCLIException:
            pass
        finally:
            if vm:
                raise VmCLIException('Object with name {} already exists, cannot clone!'.format(name))

        try:
            template = self.get_obj('vm', template)
        except VmCLIException:
            raise VmCLIException('Template {} was not found, cannot clone!'. format(template))

        datacenter = self.get_obj('datacenter', datacenter, default=True)
        self.logger.info('  * Using datacenter {}'.format(datacenter.name))
        cluster = self.get_obj('cluster', cluster, default=True)
        self.logger.info('  * Using cluster {}'.format(cluster.name))
        folder = self.get_obj('folder', folder) or datacenter.vmFolder
        self.logger.info('  * Using folder {}'.format(folder.name))
        datastore = self.get_obj('datastore', datastore) or self.get_obj('datastore', template.datastore[0].info.name)
        self.logger.info('  * Using datastore {}'.format(datastore.name))
        resource_pool = self.get_obj('resource_pool', resource_pool) or cluster.resourcePool
        self.logger.info('  * Using resource pool {}'.format(resource_pool.name))
        # build object with copy specification
        relocspec = vim.vm.RelocateSpec()
        relocspec.datastore = datastore
        relocspec.pool = resource_pool
        # build object with clone specification
        clonespec = vim.vm.CloneSpec()
        clonespec.location = relocspec
        clonespec.powerOn = poweron

        task = template.Clone(folder=folder, name=name, spec=clonespec)
        self.wait_for_tasks([task])


BaseCommands.register('clone', CloneCommands)
