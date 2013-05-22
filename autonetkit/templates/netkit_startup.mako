% for i in node.interfaces:  
/sbin/ifconfig ${i.id} ${i.ipv4_address} netmask ${i.ipv4_subnet.netmask} broadcast ${i.ipv4_subnet.broadcast} up
    % if i.speed and i.delay:
# limit interface
# heuristic burst (speed / 8 (bits->bytes) * 1024 (KB->b) / 10 (10%) => 12.8)
/sbin/orig-tc qdisc add dev {$i.id} root handle 1:0 netem delay {$i.delay}
/sbin/orig-tc qdisc add dev {$i.id} parent 1:1 handle 10: tbf limit {max(i.speed * 13, 1600)} burst {max(i.speed * 13, 1600)} rate {$i.speed}
    % endif
% endfor                                                                                                                             
route del default
/sbin/ifconfig lo 127.0.0.1 up
/etc/init.d/ssh start
/etc/init.d/hostname.sh 
/etc/init.d/zebra start
/etc/init.d/snmpd start
% if node.ssh.key:
chown -R root:root /root     
chmod 755 /root
chmod 755 /root/.ssh
chmod 644 /root/.ssh/authorized_keys
% endif
