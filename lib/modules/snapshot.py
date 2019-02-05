from pyVmomi import vim

from lib.modules import BaseCommands
from lib.tools.argparser import args
from lib.exceptions import VmCLIException


class SnapshotCommands(BaseCommands):
    """Orchestrates logic around VM snapshots."""

    def __init__(self, *args, **kwargs):
        super(SnapshotCommands, self).__init__(*args, **kwargs)

    @args('operation', help='what operation to execute', choices=['list', 'create', 'delete', 'revert'])
    @args('--name', help='name of the VM on which to operate', required=True)
    @args('--snapshot', help='name of the snapshot to create/delete/revert')
    def execute(self, args):
        if args.operation != 'list' and not args.snapshot:
            raise VmCLIException('Argument --snapshot is required with "{}" operation!'.format(args.operation))

        self.logger.info('Retrieving VM object...')
        vm = self.get_obj('vm', args.name)
        if not vm:
            raise VmCLIException('No VM with name "{}" found')

        if args.operation == 'list':
            self.list_snapshots(vm)
        elif args.operation == 'create':
            self.create_snapshot(vm, args.snapshot, args.desc, args.memory, args.quiesce)
        elif args.operation == 'delete':
            self.delete_snapshot(vm, args.snapshot)
        elif args.operation == 'revert':
            self.revert_snapshot(vm, args.snapshot)

    def list_snapshots(self, vm):
        """Lists snapshots present on the VM."""
        snap_info = vm.snapshot
        tree = snap_info.rootSnapshotList
        while tree[0].childSnapshotList is not None:
            print("Snapshot .... {}".format(tree[0].name))
            print("  desc: ..... {}".format(tree[0].description))
            print("  date: ..... {}".format(str(tree[0].createTime)))
            if len(tree[0].childSnapshotList) < 1:
                break
            tree = tree[0].childSnapshotList

    def get_snapshot_by_name(self, snapshots, name):
        """Gets first snapshot object found based on name."""
        for snap in snapshots:
            if snap.name == name:
                return snap
            else:
                return self.get_snapshot_by_name(snap.childSnapshotList, name)

    @args('--desc', help='snapshot description (required when action==create)')
    @args('--memory', help='snapshot VM memory (default is False)', action='store_true', default=False)
    @args('--quiesce', help='quiesce VM filesystem (default is True)', action='store_true', default=True)
    def create_snapshot(self, vm, snapshot, desc, memory, quiesce):
        """Creates new snapshot on the VM."""
        if desc is None:
            raise VmCLIException('Argument --desc is required with "create" operation!')

        self.logger.info('Creating snapshot of the virtual machine...')
        task = vm.CreateSnapshot_Task(name=snapshot, description=desc, memory=memory, quiesce=quiesce)
        self.wait_for_tasks([task])

    def delete_snapshot(self, vm, snapshot):
        """Deletes specific snapshot on the VM."""
        snap = self.get_snapshot_by_name(vm.snapshot.rootSnapshotList, snapshot)
        self.logger.info('Deleting snapshot from the virtual machine...')
        task = snap.snapshot.RemoveSnapshot_Task(removeChildren=False)
        self.wait_for_tasks([task])

    def revert_snapshot(self, vm, snapshot):
        """Reverts VM to a specific snapshot."""
        snap = self.get_snapshot_by_name(vm.snapshot.rootSnapshotList, snapshot)
        self.logger.info('Reverting VM to specified snapshot...')
        task = snap.snapshot.RevertToSnapshot_Task()
        self.wait_for_tasks([task])


BaseCommands.register('snapshot', SnapshotCommands)
