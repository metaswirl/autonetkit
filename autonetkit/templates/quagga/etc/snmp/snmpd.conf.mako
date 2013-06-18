#
#  AGENT BEHAVIOUR
#

#  Listen for connections on all interfaces (both IPv4 *and* IPv6)
agentAddress udp:161

# only allow access from local/tap/same asn
# v2c
rocommunity public 127.0.0.1
rocommunity public 10.${node.asn-1}.0.0/16
rocommunity public ${'.'.join(str(node.tap.ip).split('.')[:2])}.0.0/16

# v3
rouser foo # password "foofoofoo"

#
# Override for speed
#
% for interface in node.interfaces:  
    % if interface.speed: ## traffic control needs speed and delay!
override iso.3.6.1.2.1.2.2.1.5.${interface.speed.iface} uinteger ${interface.speed.limit}
    % endif 
% endfor
% if node.isis: 
override iso.3.6.1.2.1.138.1.1.1.3 octet_str "${node.isis.net_bit_str}"
% endif

#
#  AgentX Sub-agents
#
master          agentx
agentXSocket   /var/agentx/master
agentXPerms    0666 0666 nobody nogroup
