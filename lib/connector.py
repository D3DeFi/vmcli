import ssl
import getpass
import requests
import atexit
import sys
from pyVmomi import vim
from pyVim.connect import SmartConnect, Disconnect

from lib import config as conf
from lib.tools.logger import logger


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
    except vim.fault.InvalidLogin as e:
        logger.error('Unable to connect. Check your credentials!')
        sys.exit(1)
    except (requests.exceptions.SSLError, requests.exceptions.ConnectionError) as e:
        logger.error(e.message)
        sys.exit(1)
