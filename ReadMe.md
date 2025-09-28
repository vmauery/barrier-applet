# Barrier Applet

This is a python GTK system-tray applet intended to control the
[Input Leap](https://github.com/input-leap/input-leap.git) application
based on screensaver status.

I know that Input Leap comes with a tray applet, but I wanted more control
over the behavior, so I made this.

My setup is a little complicated because connecting to a Windows+WSL2
setup on a separate network made it a little tricky. The complication
is probably all my fault, but this works for me.

On the windows side, I have a screen opening an SSH tunnel to the Linux
system to determine what mode to run in (server or client) and allowing
traffic to go securely through the tunnel.

I have added some of the helper scripts and stuff to get it all working
for me, in case that helps anyone else.
