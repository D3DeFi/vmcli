from pyVmomi import vim


LOG_LEVEL_CHOICES = [
    'NOTSET',
    'DEBUG',
    'INFO',
    'WARNING',
    'ERROR',
    'CRITICAL'
]

VMWARE_TYPES = {
    'vm': vim.VirtualMachine,
    'datacenter': vim.Datacenter,
    'folder': vim.Folder,
    'cluster': vim.ClusterComputeResource,
    'datastore': vim.Datastore,
    'datastore_cluster': vim.StoragePod,
    'resource_pool': vim.ResourcePool,
    'network': vim.Network,
    'dvs_portgroup': vim.dvs.DistributedVirtualPortgroup
}

VM_MIN_CPU = 1
VM_MAX_CPU = 16
VM_MIN_MEM = 256
VM_MAX_MEM = 66000
VM_MIN_HDD = 1
VM_MAX_HDD = 2000
