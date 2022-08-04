cd c:\Users\vmauery
$wsl_ip = (wsl hostname -I).trim()
ssh -n -N -T -J $wsl_ip -o ExitOnForwardFailure=yes -R 24800:localhost:24800 10.1.1.5
