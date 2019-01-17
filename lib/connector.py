import ssl
import getpass
import requests
import atexit
import sys
from pyVmomi import vim
from pyVim.connect import SmartConnect, Disconnect

from lib import config as conf
from lib.tools.logger import logger
from lib.exceptions import VmCLIException

try:
    # Vmware's vsphere-automation-sdk-python is required for advanced features like tagging on versions newer than 6+
    from com.vmware.cis_client import Session
    from com.vmware.vapi.std.errors_client import Unauthenticated
    from vmware.vapi.stdlib.client.factories import StubConfigurationFactory
    from vmware.vapi.lib.connect import get_requests_connector
    from vmware.vapi.security.session import create_session_security_context
    from vmware.vapi.security.user_password import create_user_password_security_context
    HAS_AUTOMAT_SDK_INSTALLED = True
except ImportError:
    HAS_AUTOMAT_SDK_INSTALLED = False


def connect(vcenter=None, username=None, password=None, insecure=None):
    """Creates connection object authenticated against provided vCenter. Created object can be than used
    up to user's permissions to interact with the vCenter via API."""
    # If arguments provided are None, load global directives
    vcenter = vcenter or conf.VCENTER
    username = username or conf.USERNAME
    password = password or conf.PASSWORD
    insecure = insecure or conf.INSECURE_CONNECTION
    # If only password is missing, prompt user interactively
    if (vcenter and username) and not password:
        password = getpass.getpass()
        conf.PASSWORD = password
    elif not (vcenter and username and password):
        logger.error('No authentication credentials provided!')
        sys.exit(1)

    sslContext = None
    if insecure:
        requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)
        # Create SSL context for connection without certificate checks
        sslContext = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
        sslContext.verify_mode = ssl.CERT_NONE

    connection = None
    try:
        logger.info('Trying to connect to {}...'.format(vcenter))
        # Load connection object into global variable
        connection = SmartConnect(host=vcenter, user=username, pwd=password, sslContext=sslContext)
        # Register function to be executed at termination, eg. session cleanup
        atexit.register(Disconnect, connection)
        logger.info('Connection successful!')
        return connection
    except vim.fault.InvalidLogin:
        logger.error('Unable to connect. Check your credentials!')
        sys.exit(1)
    except (requests.exceptions.SSLError, requests.exceptions.ConnectionError) as e:
        logger.error(e.message)
        sys.exit(1)


def automationSDKConnect(vcenter=None, username=None, password=None, insecure=None):
    """Creates stub_config with connection object for advanced features like VM Tagging present
    in vsphere-automation-sdk-python library, which is required to be installed:
    https://github.com/vmware/vsphere-automation-sdk-python"""
    vcenter = vcenter or conf.VCENTER
    username = username or conf.USERNAME
    password = password or conf.PASSWORD
    insecure = insecure or conf.INSECURE_CONNECTION

    if not HAS_AUTOMAT_SDK_INSTALLED:
        raise VmCLIException('Required vsphere-automation-sdk-python not installed. Exiting...')
        sys.exit(1)

    if (vcenter and username) and not password:
        password = getpass.getpass()
    elif not (vcenter and username and password):
        logger.error('No authentication credentials provided!')
        sys.exit(1)

    if not vcenter.startswith('http'):
        vcenter = 'https://{}/api'.format(vcenter)

    session = requests.Session()
    if insecure:
        requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)
        session.verify = False

    connector = get_requests_connector(session=session, url=vcenter)
    stub_config = StubConfigurationFactory.new_std_configuration(connector)

    # Pass user credentials (user/password) in the security context to authenticate.
    # login to vAPI endpoint
    user_password_security_context = create_user_password_security_context(username, password)
    stub_config.connector.set_security_context(user_password_security_context)

    # Create the stub for the session service and login by creating a session.
    session_svc = Session(stub_config)
    try:
        session_id = session_svc.create()
    except Unauthenticated:
        logger.error('Unable to connect. Check your credentials!')
        sys.exit(1)

    # Successful authentication.  Store the session identifier in the security
    # context of the stub and use that for all subsequent remote requests
    session_security_context = create_session_security_context(session_id)
    stub_config.connector.set_security_context(session_security_context)

    return stub_config
