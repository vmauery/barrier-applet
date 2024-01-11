#Set-PSDebug -Trace 1
cd c:\Users\vmauery
#$wsl_ip = (wsl hostname -I).trim()
#$vnet_ip = 172.27.48.1
#ssh -n -N -T -J $wsl_ip -o ServerAliveInterval=5 -o ExitOnForwardFailure=yes -R "localhost:24800:${vnet_ip}:24800" $client_ip
$my_ip=(Get-NetAdapter | Where-Object {$_.InterfaceDescription -Match "Realtek USB GbE Family Controller #2"} | Get-NetIPAddress -AddressFamily IPv4).IPAddress
$client_ip=10.1.1.5
#echo "localhost:24800:${my_ip}:24800" "$client_ip"
echo "ssh -n -N -T -o ServerAliveInterval=5 -o ExitOnForwardFailure=yes -R ""localhost:24800:${my_ip}:24800"" 10.1.1.5"
ssh -n -N -T -o ServerAliveInterval=5 -o ExitOnForwardFailure=yes -R "localhost:24800:${my_ip}:24800" 10.1.1.5
