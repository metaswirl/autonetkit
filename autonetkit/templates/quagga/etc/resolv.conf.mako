<% 
    if not node.dns.role == "client":
        return
%>
search ${node.dns.tld}.
nameserver ${node.dns.nameserver}
