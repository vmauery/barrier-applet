#!/usr/bin/env python3

# applet for controlling input-leap based on screensaver activity
# Copyright (C) 2021 Vernon Mauery
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

import wx.adv
import wx
import time, sys, subprocess, re, os
from pathlib import Path
from datetime import datetime
import dbus
import json
import signal

def log(msg):
    now = datetime.now()
    print("{}: {}".format(now.strftime("%Y-%m-%d-%H:%M:%S"), msg))

class ExecutionError(Exception):
    pass

class Settings(object):
    def __init__(self, fn, defaults = None):
        self.___fn = fn
        self.___defaults = defaults
        self.___values = {}
        self.load()
    def __getattribute__(self, name):
        if name.startswith("_Settings___") or name in ['load', 'save', 'values']:
            return super(Settings, self).__getattribute__(name)
        return self.___values[name]
    def __setattr__(self, name, value):
        if name.startswith("_Settings___"):
            return super(Settings, self).__setattr__(name, value)
        self.___values[name] = value
        self.save()
    def values(self):
        return self.___values
    def load(self):
        try:
            with open(self.___fn, 'r') as f:
                self.___values = json.load(f)
        except:
            self.___values = self.___defaults
    def save(self):
        self.___fn.parent.mkdir(parents=True, exist_ok=True)
        with open(self.___fn, 'w') as f:
            json.dump(self.___values, f, indent=4)
            f.write("\n")

class Input_Leap:
    SETTINGS_FILE = Path.home() / '.config' / 'input-leap' / 'input-leap-applet.conf'
    SETTINGS_DEFAULTS={ "mode": "client", "follow_screensaver": False }
    def __init__(self, server_mode=None):
        self.settings = Settings(self.SETTINGS_FILE, self.SETTINGS_DEFAULTS)
        log("input-leap(mode={})".format(server_mode))
        log("input-leap.settings = {}".format(self.settings.values()))
        if server_mode is not None:
            self.settings.mode = server_mode
        else:
            self.server_mode = self.settings.mode == "server"
        self.p = None
        if self.server_mode:
            self.log_file = Path.home() / 'var' / 'log' / 'input-leaps.log'
            self.log_filter = re.compile(r'(NOTE: accepted client connection|client "[^"]*" has disconnected)')
        else:
            self.log_file = Path.home() / 'var' / 'log' / 'input-leapc.log'
            self.log_filter = re.compile(r'(connected to server|NOTE: disconnected from server)')

    def __del__(self):
        self.stop()

    def start(self):
        if not self.running():
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            self.log_file.unlink(missing_ok=True)
            log("launching input-leap ({} mode) ...".format(self.settings.mode))
            if self.server_mode:
                pname = '/usr/bin/input-leaps'
                self.kill_others(pname)
                self.p = subprocess.Popen([pname, '--no-tray',
                    '--no-daemon', '--log', str(self.log_file)],
                        stdout=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL)
            else:
                pname = '/usr/bin/input-leapc'
                self.kill_others(pname)
                self.p = subprocess.Popen([pname, '--no-tray',
                    '--no-daemon', '--use-x11', '--log', str(self.log_file),
                    'localhost:24800'],
                        stdout=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL)
            if not self.p:
                raise ExecutionError('Failed to start input-leaps')

    def kill_others(self, others):
         for line in os.popen("ps ax | grep " + others + " | grep -v grep"):
            pid = line.split()[0]
            log("killing other {} ({})".format(others, pid))
            os.kill(int(pid), signal.SIGKILL)

    def stop(self):
        if self.running():
            log("stopping input-leap...")
            self.p.terminate()
            try:
                self.p.wait(timeout=0.5)
            except TimeoutExpired:
                self.p.kill()
            self.p.wait()
            self.p = None

    def running(self):
        if self.p is None:
            return False
        r = self.p.poll() is None
        log("input-leap alive")
        return r

    def has_connection(self):
        lines = []
        try:
            with self.log_file.open() as f:
                lines = f.readlines() 
        except:
            pass
        lines = list(filter(lambda l: self.log_filter.search(l), lines))
        if len(lines) > 0:
            if 'disconnected' in lines[-1]:
                return False
            return True
        return False

class ScreensaverStatus():
    IDLE = 60 # seconds
    def __init__(self):
        return
        self.bus = dbus.SessionBus()
    def idleTime(self):
        return 0
        idle = self.bus.call_blocking('org.xfce.ScreenSaver', '/', 'org.xfce.ScreenSaver', 'GetActiveTime', '', [])
        idle = int(idle)
        if False:
            if idle > 0:
                log("screensaver is active for {} seconds".format(idle))
            else:
                log("screensaver is inactive")
        return idle
    def isIdle(self):
        idle = self.idleTime()
        return idle > self.IDLE;

class OneArgMenu:
    def __init__(self, handler, arg, item):
        self.handler = handler
        self.arg = arg
        self.item = item
    def __call__(self, event):
        self.handler(event, self.arg, self.item)

class TaskBarIcon(wx.adv.TaskBarIcon):
    IDLE_TIMEOUT = 10 # seconds
    def __init__(self, frame):
        self.frame = frame
        super(TaskBarIcon, self).__init__()
        self.Bind(wx.adv.EVT_TASKBAR_LEFT_DOWN, self.on_left_down)
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_timer, self.timer)
        self.iconTimer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.updateIcon, self.iconTimer)
        self.input_leap = Input_Leap()
        self.saver = ScreensaverStatus()
        self.follow_screensaver = self.input_leap.settings.follow_screensaver
        if not self.follow_screensaver:
            self.start()
        else:
            if self.saver.isIdle():
                self.stop()
            else:
                self.start()

    def __del__(self):
        self.input_leap.stop()

    def active_icon(self):
        if self.input_leap.server_mode:
            return ('input-leap-active.png', 'input-leap Server Active')
        else:
            return ('input-leap-active.png', 'input-leap Client Active')

    def inhibited_icon(self):
        if self.input_leap.server_mode:
            return ('input-leap-inactive.png', 'input-leap Server Inhibited')
        else:
            return ('input-leap-inactive.png', 'input-leap Client Inhibited')

    def idle_icon(self):
        if self.input_leap.server_mode:
            return ('input-leap-idle.png', 'input-leap Server Idle')
        else:
            return ('input-leap-idle.png', 'input-leap Client Idle')


    def set_follow(self, evt, unused, item):
        self.follow_screensaver = not self.follow_screensaver
        self.input_leap.settings.follow_screensaver = self.follow_screensaver

    def set_mode(self, evt, mode, item):
        restart = self.input_leap.running()
        if mode == 1:
            if not self.input_leap.server_mode:
                self.stop()
                log("Server Mode")
                self.input_leap = Input_Leap(True)
                if restart:
                    self.start()
        else:
            if self.input_leap.server_mode:
                self.stop()
                log("Client mode!")
                self.input_leap = Input_Leap(False)
                if restart:
                    self.start()

    def CreatePopupMenu(self):
        def create_menu_item(menu, label, func, arg=None, kind=wx.ITEM_NORMAL,
                checked=False, _s=[]):
            # log("create_menu_item({}, {}, {}, {}, {}, {})".format(
            #     menu, label, func, arg, kind, checked))
            if len(_s) == 0:
                _s.append(10)
            mid = _s[0]
            _s[0] += 1
            item = wx.MenuItem(menu, mid, label, kind=kind)
            cb = OneArgMenu(func, arg, item)
            menu.Bind(wx.EVT_MENU, cb, id=item.GetId())
            menu.Append(item)
            if kind == wx.ITEM_RADIO or kind == wx.ITEM_CHECK:
                item.Check(checked)
            return item
        menu = wx.Menu()
        create_menu_item(menu, "Follow screensaver", self.set_follow, 3,
                kind=wx.ITEM_CHECK,
                checked=self.follow_screensaver)
        create_menu_item(menu, "Server Mode", self.set_mode, 1,
                kind=wx.ITEM_RADIO, checked=self.input_leap.server_mode)
        create_menu_item(menu, "Client Mode", self.set_mode, 2,
                kind=wx.ITEM_RADIO, checked=not self.input_leap.server_mode)
        menu.AppendSeparator()
        create_menu_item(menu, '10 Seconds', self.on_arm_timer, 10)
        create_menu_item(menu, '1 minute', self.on_arm_timer, 60)
        create_menu_item(menu, '30 Minutes', self.on_arm_timer, 32*60)
        create_menu_item(menu, '1 Hour', self.on_arm_timer, 62*60)
        create_menu_item(menu, '1.5 Hours', self.on_arm_timer, 92*60)
        create_menu_item(menu, '2 Hours', self.on_arm_timer, 122*60)
        menu.AppendSeparator()
        create_menu_item(menu, 'Start', self.on_start)
        create_menu_item(menu, 'Stop', self.on_stop)
        menu.AppendSeparator()
        create_menu_item(menu, 'Exit', self.on_exit)
        return menu

    def set_icon(self, choice):
        icon = wx.Icon(choice[0])
        self.SetIcon(icon, choice[1])

    def start(self):
        # log("TaskBarIcon::start")
        if not self.input_leap.running():
            self.input_leap.start()
        self.timer.Start(1000*self.IDLE_TIMEOUT, wx.TIMER_ONE_SHOT)
        self.updateIcon()

    def stop(self):
        # log("TaskBarIcon::stop")
        self.iconTimer.Stop()
        self.set_icon(self.inhibited_icon())
        if self.input_leap.running():
            self.input_leap.stop()

    def on_left_down(self, event):
        # log('Toggle on-off')
        self.timer.Stop()
        if self.input_leap.running():
            self.stop()
        else:
            self.start()

    def on_arm_timer(self, event, timeout, item):
        # log('Turn off for {} seconds'.format(timeout))
        self.stop()
        self.timer.Start(timeout*1000, wx.TIMER_ONE_SHOT)

    def on_timer(self, event):
        # log('Timeout')
        self.timer.Stop()
        if self.follow_screensaver:
            if self.saver.isIdle():
                if self.input_leap.running():
                    self.stop()
            else:
                if not self.input_leap.running():
                    self.start()
        else:
            if not self.input_leap.running():
                self.start()
        # another round!
        self.timer.Start(1000*self.IDLE_TIMEOUT, wx.TIMER_ONE_SHOT)

    def updateIcon(self, event=None):
        # log('Timeout')
        if self.input_leap.running():
            if self.input_leap.has_connection():
                self.set_icon(self.active_icon())
            else:
                self.set_icon(self.idle_icon())
        # another round!
        self.iconTimer.Start(1000, wx.TIMER_ONE_SHOT)

    def on_start(self, event, arg, item):
        # log('Turn On')
        self.timer.Stop()
        self.start()

    def on_stop(self, event, arg, item):
        # log('Turn Off')
        self.timer.Stop()
        self.stop()

    def on_exit(self, event, arg, item):
        wx.CallAfter(self.Destroy)
        self.frame.Close()

class App(wx.App):
    def OnInit(self):
        frame=wx.Frame(None)
        self.SetTopWindow(frame)
        TaskBarIcon(frame)
        return True

def main():
    app = App(False)
    app.MainLoop()


if __name__ == '__main__':
    main()
