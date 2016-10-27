from lib.modules import BaseCommands
from lib.tools.argparser import args
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
        for item in container.view:
            print(item.name.encode('utf-8'))

    @args('--name', help='search for a specific object instead')
    def show_item(self, vimtype, name):
        """Lists details about specific VMware object."""
        # TODO: format output
        obj = self.get_obj(vimtype, name, default=False)
        if obj:
            print(obj.summary)


BaseCommands.register('list', ListCommands)
