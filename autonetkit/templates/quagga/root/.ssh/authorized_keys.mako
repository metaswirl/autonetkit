<% 
    if not node.ssh.key:
        return
%>
${node.ssh.key}
