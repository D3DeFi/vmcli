from pyVmomi import vim

from lib.modules import BaseCommands
from lib.tools.argparser import args
from lib.tools import convert_to_mb
from lib.constants import VMWARE_TYPES


class ListCommands(BaseCommands):
    """display specific VMware objects and their details."""

    def __init__(self, *args, **kwargs):
        super(ListCommands, self).__init__(*args, **kwargs)

    @args('type', help='for which type of objects to search', choices=[key for key in VMWARE_TYPES.keys()])
    def execute(self, args):
        if args.name:
            self.show_item(args.type, args.name)
        else:
            self.list_items([VMWARE_TYPES[args.type]])

    def list_items(self, vimtype):
        """Lists items in a specific VMware object category."""
        container = self.content.viewManager.CreateContainerView(self.content.rootFolder, vimtype, True)
        self.logger.info('Searching for requested category...')
        for item in sorted(container.view, key=lambda x: str(x.name).lower):
            print(item.name.encode('utf-8'))

    @args('--name', help='search for a specific object instead')
    def show_item(self, vimtype, name):
        """Lists details about specific VMware object."""
        obj = self.get_obj(vimtype, name, default=False)
        if not obj:
            return

        if vimtype == 'vm':
            self.show_vm_details(obj)
        else:
            # TODO: format output
            print(obj.summary)

    def show_vm_details(self, obj):
        """Lists details about VM."""
        datacenter, folder, root_obj = self.get_vm_datacenter_details(obj)
        datastore = self.get_vm_datastore_name(obj.datastore[0].name, root_obj)
        resource_pool = obj.resourcePool.summary.name
        mem = obj.summary.config.memorySizeMB
        cpu = obj.summary.config.numCpu
        cluster = self.get_vm_cluster_name(obj.summary.runtime.host.name, root_obj)

        print('Datacenter ........ {}'.format(datacenter))
        print('Folder ............ {}'.format(folder))
        print('Datastore ......... {}'.format(datastore))
        print('Cluster ........... {}'.format(cluster))
        print('ResourcePool ...... {}'.format(resource_pool))
        print('Memory ............ {}'.format(mem))
        print('CPU ............... {}'.format(cpu))
        # Get information about hard drives
        for device in obj.config.hardware.device:
            if isinstance(device, vim.vm.device.VirtualDisk):
                devsize = device.deviceInfo.summary
                dshost = self.get_vm_datastore_name(device.backing.datastore.name, root_obj)
                devsize = convert_to_mb(devsize.replace(',', '').rstrip('B'))
                print('HDD ............... {}M ({})'.format(devsize, dshost))

        for nic in obj.network:
            print('Network ........... {}'.format(nic.summary.name))

    def get_vm_datacenter_details(self, obj):
        """Retrieves VM's folder, dc and root parent object by traversing linked list of parents back to beginning."""
        folder = 'N/A'
        datacenter = 'N/A'
        root_obj = False

        if obj.parent:
            folder = obj.parent.name
            obj_parent = obj.parent
            while obj_parent:
                root_obj = obj_parent
                # Datacenter is the latest parent
                if isinstance(obj_parent, vim.Datacenter):
                    datacenter = obj_parent.name
                    break

                obj_parent = obj_parent.parent

        return (datacenter, folder, root_obj)

    def get_vm_datastore_name(self, vm_ds_node, root_obj):
        """Retrieves name of main datastore, where VM is placed. If possible, name of datastore cluster is returned."""
        datastore = 'N/A'
        for dshost in root_obj.datastoreFolder.childEntity:
            if isinstance(dshost, vim.StoragePod):
                for ds in dshost.childEntity:
                    if ds.name == vm_ds_node:
                        return dshost.name

            elif dshost.name == vm_ds_node:
                return dshost.name
        return datastore

    def get_vm_cluster_name(self, vm_cl_node, root_obj):
        """Retrieves Compute Cluster or Node name by iterating over Compute nodes."""
        cluster = 'N/A'
        for clhost in root_obj.hostFolder.childEntity:
            if isinstance(clhost, vim.ClusterComputeResource):
                for cl in clhost.host:
                    if cl.name == vm_cl_node:
                        return clhost.name

            elif clhost.name == vm_cl_node:
                return clhost.name
        return cluster

BaseCommands.register('list', ListCommands)
