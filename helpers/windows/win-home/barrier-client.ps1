cd c:\Users\vmauery
#$wsl_ip = (wsl hostname -I).trim()
#NO_TERM="-n -N -T"
client_ip=10.1.1.5
#ssh -n -N -T -J $wsl_ip -o ServerAliveInterval=5 -o ExitOnForwardFailure=yes -L 24800:localhost:24800 $client_ip
ssh -n -N -T -o ServerAliveInterval=5 -o ExitOnForwardFailure=yes -L 24800:localhost:24800 "$client_ip"
