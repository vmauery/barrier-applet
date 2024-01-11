# Make sure WSL2 is running in mirrored networking mode:
# modify C:\Users\<user>\.wslconfig
# [wsl2]
# localhostforwarding=true
# guiApplications=true
# vmIdleTimeout=100000000
# networkingMode=mirrored
#
# Set up an event in the task scheduler
# trigger on a log: system; source: Hyper-V-VmSwitch; Event ID: 102
# Run at highest privs and when logged in
#

Get-NetAdapter | Where-Object {$_.InterfaceDescription -Match "PANGP Virtual Ethernet Adapter Secure"} | Set-NetIPInterface -InterfaceMetric 10
$wired_if=(Get-NetAdapter | Where-Object {$_.InterfaceDescription -Match "Realtek USB GbE Family Controller #2"}).ifIndex
route delete 10.1.1.5 mask 255.255.255.255
route add 10.1.1.5 mask 255.255.255.255 0.0.0.0 if "$wired_if" metric 1
