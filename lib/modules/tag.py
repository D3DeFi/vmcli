import sys

from lib.modules import BaseCommands
from lib.tools.argparser import args
from lib.connector import automationSDKConnect
from lib.exceptions import VmCLIException

try:
    from com.vmware.cis.tagging_client import Tag, TagAssociation
    from com.vmware.vapi.std_client import DynamicID
    HAS_AUTOMAT_SDK_INSTALLED = True
except ImportError:
    HAS_AUTOMAT_SDK_INSTALLED = False


class TagCommands(BaseCommands):
    """Allows managing Tags fetaure in Vcenter 6+ versions."""

    def __init__(self, *args, **kwargs):
        super(TagCommands, self).__init__(*args, **kwargs)

    def execute(self, args):
        if not HAS_AUTOMAT_SDK_INSTALLED:
            raise VmCLIException('Required vsphere-automation-sdk-python not installed. Exiting...')
            sys.exit(1)

        stub_config = automationSDKConnect(args.vcenter, args.username, args.password, args.insecure)

        if args.name:
            self.associate_tag(stub_config, args.name, args.tags)
        else:
            self.print_tags(stub_config)

    def print_tags(self, stub_config):
        """Prints available tags for user."""
        tag_svc = Tag(stub_config)
        for t in tag_svc.list():
            tag = tag_svc.get(t)
            print(tag.name)

    @args('--tags', help='Tag names to associate with VM e.g. tag1,tag2')
    @args('--name', help='name of VM to associate tags to')
    def associate_tag(self, stub_config, name, tags):
        """Associates tags with specific VM."""
        if not name or not tags:
            raise VmCLIException('Arguments name or tags are missing, cannot continue!')

        self.logger.info('Retreiving VM and Tag objects...')
        vm = self.get_obj('vm', name)
        if not vm:
            raise VmCLIException('No VM with name "{}" found')
        # Get vmware ID representation in form 'vm-XXX' for later association
        vm_id = vm._GetMoId()
        vm_dynid = DynamicID(type='VirtualMachine', id=vm_id)
        # Create API services for Tag and TagAssociation backends
        tag_svc = Tag(stub_config)
        tag_asoc = TagAssociation(stub_config)
        # Search for tag object(s)
        tags_found = []
        if ',' in tags:
            tags = tags.split(',')
        else:
            tags = [tags]

        for t in tag_svc.list():
            tag = tag_svc.get(t)
            if tag.name in tags:
                tags_found.append(tag)

        if len(tags_found) != len(tags):
            raise VmCLIException('One or more tags were not found')

        # Asosociate tags with VM
        for tag in tags_found:
            tag_asoc.attach(tag_id=tag.id, object_id=vm_dynid)
        self.logger.info('All tags have been attached to the VM')


BaseCommands.register('tag', TagCommands)
