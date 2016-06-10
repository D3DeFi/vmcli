Description
-----------
Vmcli aims to provide command line tool to allow virtual machine management and delivery by interacting with VMware's vSphere API. It implements simple methods and classes for modules expansion, making addition of new vmcli subcommands easy as inheriting classes in the Python programming language.

Other aim is to make as much directives configurable as possible. Options can be provided via default values, command line arguments, configuration file directives and environment variables. For the create or clone subcommands there are flavors too, these represents templates for virtual machine's hardware configuration.

Installation
------------

To begin using vmcli you need to have python2.7, python-virtualenv and python-pip packages installed. Then execute the following steps:
```
  virtualenv env
  source env/bin/activate
  pip install -r requirements.txt
  vmcli.py --help
```

Configuration directives
------------------------
 - command line arguments
 - ENV variable
 - config file
 - default
 - flavor setting (if present)

Examples
--------

Adding new/modifying commands
-----------------------------

TODO
----
 - Flavors
 - CommandSuites
 - datastore-cluster instead of single datastore
 - implement cache to speed up get_obj calls
 - upload /etc/network/interfaces
 - fix: list vm | grep <str> throws:
    UnicodeEncodeError: 'ascii' codec can't encode character u'\u0160' in position 0: ordinal not in range(128)
