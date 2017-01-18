#!/bin/bash
#
# This script changes first non-loopback interface found on host
# Should be run only after clone operation and then discarded
#

# Snippet from https://gist.github.com/tiveone/2506075
function netmask2cidr() { 
  case $1 in
      0x*)
      local hex=${1#0x*} quad=
      while [ -n "${hex}" ]; do
        local lastbut2=${hex#??*}
        quad=${quad}${quad:+.}0x${hex%${lastbut2}*}
        hex=${lastbut2}
      done
      set -- ${quad}
      ;;
  esac

  local i= len=
  local IFS=.
  for i in $1; do
    while [ ${i} != "0" ]; do
      len=$((${len} + ${i} % 2))
      i=$((${i} >> 1))
    done
  done

  echo "${len}"
}

function configure_deb_interfaces() {
	ifdown -a
	cp /etc/network/interfaces /etc/network/interfaces.bak
	cat << EOF > /etc/network/interfaces
# This file describes the network interfaces available on your system
# and how to activate them. For more information, see interfaces(5).

source /etc/network/interfaces.d/*

# The loopback network interface
auto lo
iface lo inet loopback

# The primary network interface
auto $FIRST_INT
iface $FIRST_INT inet static
        address $ADDRESS
        netmask $NETMASK
        network $NETWORK
        broadcast $BROADCAST
        gateway $GATEWAY
EOF
	ifup -a
}

function configure_rhel_interfaces() {
	systemctl stop network.service
	UUID=$(uuidgen $FIRST_INT)
	cat << EOF > /etc/sysconfig/network-scripts/ifcfg-$FIRST_INT
TYPE="Ethernet"
BOOTPROTO="none"
DEFROUTE="yes"
IPV4_FAILURE_FATAL="no"
IPV6INIT="no"
IPV6_AUTOCONF="yes"
IPV6_DEFROUTE="yes"
IPV6_PEERDNS="yes"
IPV6_PEERROUTES="yes"
IPV6_FAILURE_FATAL="no"
IPV6_ADDR_GEN_MODE="stable-privacy"
NAME="${FIRST_INT}"
UUID="${UUID}"
DEVICE="${FIRST_INT}"
ONBOOT="yes"
IPADDR="${ADDRESS}"
PREFIX="${CIDR}"
GATEWAY="${GATEWAY}"
EOF
	systemctl start network.service		
}

OS_DIST=$(egrep '^ID=' /etc/os-release | sed 's/"//g' | awk -F'=' '{print $2}'| tr '[:upper:]' '[:lower:]')
FIRST_INT=$(ip link | egrep '^[1-9]:' | grep -v lo: | awk '{print $2}' | sed 's/://')

if [[ $# -lt 5 ]];
then
	echo "Usage: $0 IP_address netmask gateway network broadcast"
	echo "Usage: $0 192.168.1.5 255.255.255.0 192.168.1.1 192.168.1.0 192.168.1.255"
else
	ADDRESS=$1
	NETMASK=$2
	GATEWAY=$3
	NETWORK=$4
	BROADCAST=$5
	CIDR=$(netmask2cidr $NETMASK)
	if [[ $OS_DIST == 'debian' ]] || [[ $OS_DIST == 'ubuntu' ]];
	then
		configure_deb_interfaces
	fi

	if [[ $OS_DIST == 'centos' ]];
	then
		configure_rhel_interfaces
	fi
fi
