cd c:\Users\vmauery
$wsl_ip = (wsl hostname -I).trim()
$vnet_ip = 172.27.48.1
ssh -n -N -T -J $wsl_ip -o ServerAliveInterval=5 -o ExitOnForwardFailure=yes -R "localhost:24800:${vnet_ip}:24800" 10.1.1.5
