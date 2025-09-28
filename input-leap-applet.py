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

import gi
import gc
import signal
import time, sys, subprocess, re, os
from pathlib import Path
from datetime import datetime
import dbus
import json

gi.require_version('Gtk', '3.0')
gi.require_version('AppIndicator3', '0.1')

from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import AppIndicator3, Gdk, Gio, GLib, Gtk
from gi.repository.GdkPixbuf import InterpType, Pixbuf

def log(msg):
    now = datetime.now()
    print("{}: {}".format(now.strftime("%Y-%m-%d-%H:%M:%S"), msg))

class ExecutionError(Exception):
    pass

class ScreensaverStatus():
    IDLE = 60 # seconds
    def __init__(self, bus):
        self.bus = bus
        self.handler = None

    def idleTime(self):
        return 0
        idle = self.bus.call_blocking('org.gnome.ScreenSaver',
                                      '/org/gnome/ScreenSaver',
                                      'org.gnome.ScreenSaver',
                                      'GetActiveTime', '', [])
        idle = int(idle)
        if False:
            if idle > 0:
                log("screensaver is active for {} seconds".format(idle))
            else:
                log("screensaver is inactive")
        return idle
    def isIdle(self):
        idle = self.idleTime()
        return idle > self.IDLE

    def _unlock_handler(self, is_active):
        print(f"org.gnome.ScreenSaver ActiveChanged -> {is_active}")
        if not is_active and self.handler:
            self.handler()

    def unlock_callback(self, handler):
        self.handler = handler
        self.bus.add_signal_receiver(self._unlock_handler,
                                     dbus_interface='org.gnome.ScreenSaver', 
                                     signal_name='ActiveChanged',
                                     bus_name='org.gnome.ScreenSaver')


class ScreensaverInhibit:
    def __init__(self, bus):
        self.cookie = None
        self.bus = bus
        self.proxy = self.bus.get_object('org.freedesktop.ScreenSaver',
                                         '/org/freedesktop/ScreenSaver')
        self.iface = dbus.Interface(self.proxy, 'org.freedesktop.ScreenSaver')
        self.cookie = self.iface.Inhibit('work-inhibitor', "gnome-inhibit")
        print("Inhibiting screensaver (pid: {}, cookie {})".format(
            os.getpid(), self.cookie))
    def __del__(self):
        if self.cookie is not None:
            print("UnInhibiting screensaver (pid: {}, cookie {})".format(
                os.getpid(), self.cookie))
            self.iface.UnInhibit(self.cookie)

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
    INACTIVE = 0
    ACTIVE = 1
    IDLE = 2
    def __init__(self, server_mode=None):
        self.current_icon = self.INACTIVE
        self.p = None
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
                pname = '/usr/local/bin/input-leaps'
                self.kill_others(pname)
                self.p = subprocess.Popen([pname, '--no-tray',
                    '--no-daemon', '--restart', '--log', str(self.log_file)],
                        stdout=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL)
            else:
                pname = '/usr/local/bin/input-leapc'
                self.kill_others(pname)
                self.p = subprocess.Popen([pname, '--no-tray',
                    '--no-daemon', '--use-x11', '--restart',
                    '--log', str(self.log_file), '10.1.1.4:24800'],
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

    def running(self, current_icon=None):
        r = False
        pid = ""
        if self.p is not None:
            r = self.p.poll() is None
            pid = f" ({self.p.pid})"
        msg = ""
        if current_icon is None:
            current_icon = self.current_icon
        msg = ", {}".format(("inactive", "active", "idle")[current_icon])
        log(f"input-leap alive: {r}{pid}{msg}")
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

def appdir():
    return os.path.dirname(os.path.realpath(__file__))

class InputLeapApplication(Gtk.Application):
    IDLE_TIMEOUT = 10 # seconds

    def __init__(self):
        # mechanism to capture timeout_source ID
        self.delay_id = None

        self.indicator = AppIndicator3.Indicator.new(
            'Input-Leap-Control',
            'input-leap-messages',
            AppIndicator3.IndicatorCategory.APPLICATION_STATUS,
        )
        self.indicator.set_icon_theme_path(f"{appdir()}/media")
        self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)

        self.bus = dbus.SessionBus()

        self.input_leap = Input_Leap()
        self.saver = ScreensaverStatus(self.bus)
        self.saver.unlock_callback(self.restart_daemon)

        self.follow_screensaver = self.input_leap.settings.follow_screensaver
        self.screensaver_inhibitor = None

        if not self.follow_screensaver:
            self.start()
        else:
            if self.saver.isIdle():
                self.stop()
            else:
                self.start()

        self.set_icon(self.inhibited_icon())

        self.menu = Gtk.Menu()
        self.indicator.set_menu(self.menu)

        self.menu_follow_screensaver = Gtk.CheckMenuItem(
            label='Follow Screensaver', active=self.follow_screensaver)
        self.menu_server_mode = Gtk.RadioMenuItem(
                label='Server Mode', active=self.input_leap.server_mode)
        self.menu_client_mode = Gtk.RadioMenuItem(
                label='Client Mode', active=not self.input_leap.server_mode,
                group=self.menu_server_mode)
        self.menu_delay_1s = Gtk.MenuItem(label='Restart')
        self.menu_delay_10s = Gtk.MenuItem(label='10 Seconds')
        self.menu_delay_60s = Gtk.MenuItem(label='1 Minute')
        self.menu_delay_30m = Gtk.MenuItem(label='30 Minutes')
        self.menu_delay_60m = Gtk.MenuItem(label='1 Hour')
        self.menu_delay_90m = Gtk.MenuItem(label='1.5 Hours')
        self.menu_delay_120m = Gtk.MenuItem(label='2 Hours')
        self.menu_service_start= Gtk.MenuItem(label='Start')
        self.menu_service_stop = Gtk.MenuItem(label='Stop')
        self.menu_service_toggle = Gtk.MenuItem(label='Toggle')
        self.menu_quit = Gtk.MenuItem(label='Exit')

        self.menu_follow_screensaver.connect('activate', self.set_follow)
        self.menu_delay_1s.connect('activate', self.delay_handler, 1)
        self.menu_delay_10s.connect('activate', self.delay_handler, 10)
        self.menu_delay_60s.connect('activate', self.delay_handler, 60)
        self.menu_delay_30m.connect('activate', self.delay_handler, 30 * 60)
        self.menu_delay_60m.connect('activate', self.delay_handler, 60 * 60)
        self.menu_delay_90m.connect('activate', self.delay_handler, 90 * 60)
        self.menu_delay_120m.connect('activate', self.delay_handler, 120 * 60)
        self.menu_service_start.connect('activate', self.service_start_handler)
        self.menu_service_stop.connect('activate', self.service_stop_handler)
        self.menu_service_toggle.connect('activate', self.service_toggle_handler)
        self.menu_quit.connect('activate', self.quit_handler)

        # toggle on / off on middle click
        self.indicator.set_secondary_activate_target(self.menu_service_toggle)

        self.menu.append(self.menu_follow_screensaver)
        self.menu.append(self.menu_server_mode)
        self.menu.append(self.menu_client_mode)
        self.menu.append(Gtk.SeparatorMenuItem())
        self.menu.append(self.menu_delay_1s)
        self.menu.append(self.menu_delay_10s)
        self.menu.append(self.menu_delay_60s)
        self.menu.append(self.menu_delay_30m)
        self.menu.append(self.menu_delay_60m)
        self.menu.append(self.menu_delay_90m)
        self.menu.append(self.menu_delay_120m)
        self.menu.append(Gtk.SeparatorMenuItem())
        self.menu.append(self.menu_service_start)
        self.menu.append(self.menu_service_stop)
        self.menu.append(Gtk.SeparatorMenuItem())
        self.menu.append(self.menu_quit)

        GLib.timeout_add_seconds(30, self.collect_garbage)
        GLib.timeout_add_seconds(1, self.status_timer)

        self.menu.show_all()

    def __del__(self):
        self.input_leap.stop()

    def restart_daemon(self, *args, **kwargs):
        print("restarting because of screen unlock")
        self.delay_handler(None, 1)

    def delay_handler(self, widget, timeout):
        print(f"delay_handler({timeout})")
        self.stop()
        self.stop_delay_timer()
        self.delay_id = GLib.timeout_add_seconds(timeout, self.delayed_start)

    def delayed_start(self):
        print("delayed_start")
        self.stop_delay_timer()
        self.start()
        return GLib.SOURCE_REMOVE

    def active_icon(self):
        if self.input_leap.server_mode:
            self.input_leap.current_icon = self.input_leap.ACTIVE
            return ('input-leap-active', 'input-leap Server Active')
        else:
            if self.input_leap.current_icon != self.input_leap.ACTIVE:
                self.screensaver_inhibitor = ScreensaverInhibit(self.bus)
                pass
            self.input_leap.current_icon = self.input_leap.ACTIVE
            return ('input-leap-active', 'input-leap Client Active')

    def inhibited_icon(self):
        self.input_leap.current_icon = self.input_leap.INACTIVE
        if self.input_leap.server_mode:
            return ('input-leap-inactive', 'input-leap Server Inhibited')
        else:
            self.screensaver_inhibitor = None
            return ('input-leap-inactive', 'input-leap Client Inhibited')

    def idle_icon(self):
        self.input_leap.current_icon = self.input_leap.IDLE
        if self.input_leap.server_mode:
            return ('input-leap-idle', 'input-leap Server Idle')
        else:
            self.input_leap.current_icon = self.input_leap.IDLE
            self.screensaver_inhibitor = None
            return ('input-leap-idle', 'input-leap Client Idle')

    def set_follow(self, *args, **kwargs):
        self.follow_screensaver = not self.follow_screensaver
        self.input_leap.settings.follow_screensaver = self.follow_screensaver

    def set_mode(self, *args, **kwargs):
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

    @staticmethod
    def collect_garbage():
        gc.collect()
        return GLib.SOURCE_CONTINUE

    def set_icon(self, choice):
        self.indicator.set_icon_full(*choice)

    def start(self):
        # log("TaskBarIcon::start")
        if not self.input_leap.running():
            self.input_leap.start()
        self.set_icon(self.idle_icon())

    def stop(self):
        # log("TaskBarIcon::stop")
        self.set_icon(self.inhibited_icon())
        if self.input_leap.running():
            self.input_leap.stop()

    def on_arm_timer(self, event, timeout, item):
        # log('Turn off for {} seconds'.format(timeout))
        self.stop()

    def updateIcon(self):
        # log('Timeout')
        if self.input_leap.running(self.input_leap.current_icon):
            if self.input_leap.has_connection():
                self.set_icon(self.active_icon())
            else:
                self.set_icon(self.idle_icon())

    def service_start_handler(self, *args, **kwargs):
        # log('Turn On')
        self.start()

    def service_stop_handler(self, *args, **kwargs):
        # log('Turn Off')
        self.stop()

    def service_toggle_handler(self, *args, **kwargs):
        # log('Toggle on-off')
        if self.input_leap.running():
            self.stop()
        else:
            self.start()

    def quit_handler(self, *args, **kwargs):
        gtk_quit()

    def stop_delay_timer(self):
        # cancel the prior off
        if self.delay_id is not None:
            GLib.source_remove(self.delay_id)
            self.delay_id = None

    def status_timer(self):
        # log('Timeout')
        if self.follow_screensaver:
            if self.saver.isIdle():
                if self.input_leap.running():
                    self.stop()
            else:
                if not self.input_leap.running():
                    self.start()
        else:
            if self.input_leap.current_icon != self.input_leap.INACTIVE:
                if not self.input_leap.running():
                    self.start()
        self.updateIcon()
        # another round!
        return GLib.SOURCE_CONTINUE

def gtk_quit(*args, **kwargs):
    Gtk.main_quit()

def main():
    DBusGMainLoop(set_as_default=True)
    signal.signal(signal.SIGINT, gtk_quit)
    app = InputLeapApplication()
    Gtk.main()

if __name__ == '__main__':
    main()
