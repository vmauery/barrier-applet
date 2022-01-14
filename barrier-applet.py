#!/usr/bin/env python3

# applet for controlling barriers based on screensaver activity
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
import time, sys, subprocess

class ExecutionError(Exception):
    pass

class Barrier:
    def __init__(self):
        self.p = None

    def __del__(self):
        self.stop()

    def start(self):
        if not self.running():
            # print("launching barrier...")
            self.p = subprocess.Popen(['/usr/bin/barriers', '--no-tray', '--no-daemon'],
                    stdout=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL)
            if not self.p:
                raise ExecutionError('Failed to start barriers')

    def stop(self):
        if self.running():
            # print("stopping barrier...")
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
        return self.p.poll() is None

class ScreensaverStatus():
    IDLE = 60 # seconds
    def __init__(self):
        self.wasBlanked = self.isBlanked()
        self.time = time.time()

    def isBlanked(self):
        p = subprocess.run(['/usr/bin/xfce4-screensaver-command', '--query'],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL)
        words = p.stdout.decode().split()
        blank = 'inactive' not in words
        # print("screensaver is {}active".format({True:'',False:'in'}[blank]))
        return blank

    def isIdle(self):
        now = time.time()
        if self.isBlanked():
            # newly blanked status
            if not self.wasBlanked:
                self.wasBlanked = True
                self.time = now
            # how long idle?
            elif now - self.time > self.IDLE:
                # print('isIdle: IDLE {}'.format(now))
                return True
        else:
            self.wasBlanked = False
        # print('isIdle: BUSY {}'.format(now))
        return False

class OneArgMenu:
    def __init__(self, handler, arg):
        self.handler = handler
        self.arg = arg
    def __call__(self, event):
        self.handler(event, self.arg)

class TaskBarIcon(wx.adv.TaskBarIcon):
    BARRIER_INHIBITED = ('barrier-inactive.png', 'Barrier Inhibited')
    BARRIER_ACTIVE = ('barrier-active.png', 'Barrier Active')
    IDLE_TIMEOUT = 10 # seconds
    def __init__(self, frame):
        self.frame = frame
        super(TaskBarIcon, self).__init__()
        self.Bind(wx.adv.EVT_TASKBAR_LEFT_DOWN, self.on_left_down)
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_timer, self.timer)
        self.barrier = Barrier()
        self.saver = ScreensaverStatus()
        if not self.saver.isIdle():
            self.start()
        else:
            self.stop()

    def __del__(self):
        self.barrier.stop()

    def CreatePopupMenu(self):
        def create_menu_item(menu, label, func):
            item = wx.MenuItem(menu, -1, label)
            menu.Bind(wx.EVT_MENU, func, id=item.GetId())
            menu.Append(item)
            return item
        menu = wx.Menu()
        create_menu_item(menu, '10 Seconds', OneArgMenu(self.on_arm_timer, 10))
        create_menu_item(menu, '30 Minutes', OneArgMenu(self.on_arm_timer, 32*60))
        create_menu_item(menu, '1 Hour', OneArgMenu(self.on_arm_timer, 62*60))
        create_menu_item(menu, '1.5 Hours', OneArgMenu(self.on_arm_timer, 92*60))
        create_menu_item(menu, '2 Hours', OneArgMenu(self.on_arm_timer, 122*60))
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
        # print("TaskBarIcon::start")
        self.set_icon(self.BARRIER_ACTIVE)
        if not self.barrier.running():
            self.barrier.start()
        self.timer.Start(1000*self.IDLE_TIMEOUT, wx.TIMER_ONE_SHOT)

    def stop(self):
        # print("TaskBarIcon::stop")
        self.set_icon(self.BARRIER_INHIBITED)
        if self.barrier.running():
            self.barrier.stop()

    def on_left_down(self, event):
        # print('Toggle on-off')
        self.timer.Stop()
        if self.barrier.running():
            self.stop()
        else:
            self.start()

    def on_arm_timer(self, event, timeout):
        # print('Turn off for {} seconds'.format(timeout))
        self.stop()
        self.timer.Start(timeout*1000, wx.TIMER_ONE_SHOT)

    def on_timer(self, event):
        # print('Timeout')
        self.timer.Stop()
        if self.saver.isIdle():
            if self.barrier.running():
                self.stop()
        else:
            if not self.barrier.running():
                self.start()
        # another round!
        self.timer.Start(1000*self.IDLE_TIMEOUT, wx.TIMER_ONE_SHOT)

    def on_start(self, event):
        # print('Turn On')
        self.timer.Stop()
        self.start()

    def on_stop(self, event):
        # print('Turn Off')
        self.timer.Stop()
        self.stop()

    def on_exit(self, event):
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
