from pyVmomi import vim

from lib.modules import BaseCommands
from lib.tools import normalize_memory
from lib.tools.argparser import args
from lib.exceptions import VmCLIException
from flavors import load_vm_flavor

import lib.config as conf


class CloneCommands(BaseCommands):
    """clone specific VMware objects, without any further configuration."""

    def __init__(self, *args, **kwargs):
        super(CloneCommands, self).__init__(*args, **kwargs)

    @args('--name', required=True, help='name for a cloned object')
    @args('--template', help='template object to use as a source of cloning', map='VM_TEMPLATE')
    def execute(self, args):
        try:
            self.clone_vm(args.name, args.template, args.datacenter, args.folder, args.datastore,
                    args.cluster, args.resource_pool, args.poweron, args.mem, args.cpu, args.flavor)
        except VmCLIException as e:
            self.exit(e.message, errno=2)

    @args('--flavor', help='flavor to use for a vm cloning')
    @args('--datacenter', help='datacenter where to create vm', map='VM_DATACENTER')
    @args('--folder', help='folder where to place vm', map='VM_FOLDER')
    @args('--datastore', help='datastore where to store vm', map='VM_DATASTORE')
    @args('--cluster', help='cluster where to spawn mv', map='VM_CLUSTER')
    @args('--resource-pool', help='resource pool, which should be used for vm', map='VM_RESOURCE_POOL')
    @args('--mem', help='memory to set for a vm in megabytes', map='VM_MEM')
    @args('--cpu', help='cpu count to set for a vm', type=int, map='VM_CPU')
    @args('--poweron', help='whether to power on vm after cloning', action='store_true', map='VM_POWERON')
    def clone_vm(self, name, template, datacenter=None, folder=None, datastore=None, cluster=None,
                resource_pool=None, poweron=None, mem=None, cpu=None, flavor=None):
        """Clones new virtual machine from a template or any other existing machine."""
        flavor = load_vm_flavor(flavor)

        # TODO: let script fail when user specifies something wrong instead of using vcenter defaults
        # E.g.: ./vmcli.py create --folder non-existing will now pick Root folder of vcenter
        # load needed variables
        self.logger.info('Loading required VMware resources...')
        if mem:
            mem = normalize_memory(mem)
        template = self.get_obj('vm', template)
        datacenter = self.get_obj('datacenter', datacenter, default=True)
        cluster = self.get_obj('cluster', cluster, default=True)
        folder = self.get_obj('folder', folder) or datacenter.vmFolder
        resource_pool = self.get_obj('resource_pool', resource_pool) or cluster.resourcePool

        # Search first for datastore cluster, then for specific datastore
        datastore = datastore or template.datastore[0].info.name
        ds = self.get_obj('datastore_cluster', datastore)
        ds_type = 'cluster'
        if not ds:
            ds = self.get_obj('datastore', datastore)
            ds_type = 'specific'
            if not ds:
                self.exit('Neither datastore cluster or specific datastore is matching {}. Exiting...'.format(
                        datastore))
        datastore = ds

        if self.get_obj('vm', name):
            self.exit('VM with name {} already exists. Exiting...'.format(name))

        if not template:
            self.exit('Specified template does not exists. Exiting...')

        self.logger.info('  * Using datacenter..........{}'.format(datacenter.name))
        self.logger.info('  * Using cluster.............{}'.format(cluster.name))
        self.logger.info('  * Using folder..............{}'.format(folder.name))
        self.logger.info('  * Using datastore...........{}'.format(datastore.name))
        self.logger.info('  * Using resource pool.......{}'.format(resource_pool.name))

        self.logger.info('Running cloning operation...')
        if ds_type == 'cluster':
            storagespec = vim.storageDrs.StoragePlacementSpec(
                    cloneName=name, vm=template, resourcePool=resource_pool, folder=folder, type='clone')
            storagespec.cloneSpec = vim.vm.CloneSpec(location=vim.vm.RelocateSpec(pool=resource_pool), powerOn=poweron)
            storagespec.cloneSpec.config = vim.vm.ConfigSpec(name=name, memoryMB=mem, numCPUs=cpu, annotation=name)
            storagespec.podSelectionSpec = vim.storageDrs.PodSelectionSpec(storagePod=datastore)
            storagePlacementResult = self.content.storageResourceManager.RecommendDatastores(storageSpec=storagespec)

            try:
                # Pick first recommendation as vSphere Client does
                drs_key = storagePlacementResult.recommendations[0].key
                if not drs_key:
                    raise ValueError
            except ValueError:
                self.exit('No storage DRS recommentation provided for cluster {}, exiting...'.format(datastore.name))

            task = self.content.storageResourceManager.ApplyStorageDrsRecommendation_Task(drs_key)
            self.wait_for_tasks([task])

        elif ds_type == 'specific':
            relocspec = vim.vm.RelocateSpec(datastore=datastore, pool=resource_pool)
            configspec = vim.vm.ConfigSpec(name=name, memoryMB=mem, numCPUs=cpu, annotation=name)
            clonespec = vim.vm.CloneSpec(config=configspec, location=relocspec, powerOn=poweron)

            task = template.Clone(folder=folder, name=name, spec=clonespec)
            self.wait_for_tasks([task])


BaseCommands.register('clone', CloneCommands)
