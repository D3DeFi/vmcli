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

Options can be provided and overriden in a variety of ways. Foremost being command line arguments. Specific ways to provide configuration to the vmcli program are explained below <strong>in the exact order as they are prioritized.</strong>

### 1. Command line arguments

Arguments being most straightforward way to pass configuration options to the running program. All the available command line arguments can be found via --help argument passed to the program like this - ```vmcli.py --help```.

Help argument (--help) can be passed to any subcommand as well. Available subcommands of the vmcli program are listed in the positional arguments section of the help output delivered by main program (shown with the command above).

### 2. Flavors (For clone and create operations only)

Flavors are specific feature for virtual machine deploy operations such as create, create-empty or clone. They work similar to flavors used in any other tools or virtualization platforms (OpenStack's flavors, AWS's instance types, etc.) and can be defined by the user himself. 

To define custom flavor, **start with copying file** examples/test_flavor.py.example into flavors/**some-name**.py. The name you choose will be later used when pointing vmcli program to flavor you wish to use. This file contains only Python dictionary representation of data.


**Fill each row** as you desire respecting formatting and data types in examples (quoted strings, integers or booleans). If you want to omit some directives, simply delete entire row or type in None as a value: ```'folder': None,``` and that value will be fetched from other sources listed in this section.

When flavor is finally defined, you can provide ```--flavor some-name``` option to one of the subcommands which support flavors. For example: ```./vmcli.py create --flavor m1_tiny``` 

### 3. Environment variables
### 4. Config file (yaml)
### 5. Default values

Examples
--------

Adding new/modifying commands
-----------------------------

TODO
----

 - implement cache to speed up get_obj calls
 - fix: list vm | grep <str> throws:
    UnicodeEncodeError: 'ascii' codec can't encode character u'\u0160' in position 0: ordinal not in range(128)
