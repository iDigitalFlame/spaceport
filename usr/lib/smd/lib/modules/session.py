#!/usr/bin/false
# Module: Session (User)
#
# Manages the User's startup and session processes.
#
# System Management Daemon
#
# Copyright (C) 2016 - 2021 iDigitalFlame
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

from sched import scheduler
from time import time, sleep
from os import environ, kill
from signal import SIGCONT, SIGSTOP
from lib.modules.background import background
from lib.util import stop, boolean, eval_env, run
from subprocess import Popen, DEVNULL, SubprocessError
from lib.constants import (
    HOOK_LOCK,
    HOOK_POWER,
    HOOK_DAEMON,
    HOOK_RELOAD,
    HOOK_ROTATE,
    HOOK_SUSPEND,
    HOOK_DISPLAY,
    HOOK_SHUTDOWN,
    HOOK_HIBERNATE,
    MESSAGE_TYPE_PRE,
    MESSAGE_TYPE_POST,
    DIRECTORY_LIBEXEC,
    SESSION_WINDOW_LIST,
    DEFAULT_SESSION_TAP,
    BACKGROUND_EXEC_AUTO,
    DEFAULT_SESSION_IGNORE,
    DEFAULT_SESSION_FREEZE,
    DEFAULT_SESSION_MONITOR,
    DEFAULT_SESSION_COMPOSER,
    DEFAULT_SESSION_STARTUPS,
    DEFAULT_BACKGROUND_SWITCH,
)

HOOKS = {
    HOOK_LOCK: "Session.freeze",
    HOOK_DAEMON: "Session.thread",
    HOOK_POWER: "Session.profile",
    HOOK_RELOAD: "Session.reload",
    HOOK_ROTATE: "Session.profile",
    HOOK_SHUTDOWN: "Session.reload",
    HOOK_DISPLAY: "Session.profile",
    HOOK_SUSPEND: "Session.profile",
    HOOK_HIBERNATE: "Session.profile",
}


def _get_profile(server, name):
    profile = server.get_config(f"profile.{name}", None, False)
    if profile is None:
        server.set_config(f"profile.{name}", list(), True)
        return None
    if len(profile) == 0:
        return None
    return profile


class Session(object):
    def __init__(self):
        self.composer = None
        self.switch_time = 0
        self.running = list()
        self.profiles = dict()
        self.switch_event = None
        self.auto_monitor = False
        self.freeze_ignore = None
        self.freeze_windows = False
        self.scheduler = scheduler(timefunc=time, delayfunc=sleep)

    def setup(self, server):
        self.auto_monitor = boolean(
            server.get_config("session.auto_monitor", DEFAULT_SESSION_MONITOR, True)
        )
        try:
            self.switch_time = int(
                server.get_config(
                    "background.auto_change", DEFAULT_BACKGROUND_SWITCH, True
                )
            )
        except (TypeError, ValueError) as err:
            server.error(
                'Improper value for "background.autochange"! Resetting to default!',
                err=err,
            )
            self.switch_time = int(
                server.set_config(
                    "background.auto_change", DEFAULT_BACKGROUND_SWITCH, True
                )
            )
        composer = server.get_config("session.composer", DEFAULT_SESSION_COMPOSER, True)
        if len(composer) > 0:
            if isinstance(composer, list):
                composer = composer.copy()
            elif not isinstance(composer, str):
                server.error(
                    'Improper value for "session.composer"! Resetting to default!'
                )
                server.set_config("session.composer", DEFAULT_SESSION_COMPOSER, True)
                composer = DEFAULT_SESSION_COMPOSER
            if isinstance(composer, str):
                composer = composer.split(" ")
        if isinstance(composer, list):
            for x in range(0, len(composer)):
                composer[x] = eval_env(composer[x])
            try:
                self.composer = Popen(
                    composer, stderr=DEVNULL, stdout=DEVNULL, env=environ
                )
            except (OSError, SubprocessError) as err:
                server.error(
                    f'Starting the composer "{" ".join(composer)}" raised an Exception!',
                    err=err,
                )
        del composer
        tap = server.get_config("session.enable_tap", DEFAULT_SESSION_TAP, True)
        if tap is not None and boolean(tap):
            server.debug("Enabling Tap..")
            try:
                run([f"{DIRECTORY_LIBEXEC}/smd-enable-tap"], ignore_errors=False)
            except OSError as err:
                server.warning("Enabling Tap raised and Exception!", err=err)
        del tap
        startups = server.get_config("session.startups", DEFAULT_SESSION_STARTUPS)
        if isinstance(startups, list) and len(startups) > 0:
            for start in startups:
                try:
                    self.running.append(
                        Popen(
                            eval_env(start).split(" "),
                            env=environ,
                            stdout=DEVNULL,
                            stderr=DEVNULL,
                        )
                    )
                except (OSError, SubprocessError) as err:
                    server.warning(
                        f'Launching startup process "{start}" raised an Exception!',
                        err=err,
                    )
        del startups
        self.freeze_ignore = server.get_config(
            "session.freeze.ignore", DEFAULT_SESSION_IGNORE, True
        )
        if self.freeze_ignore is not None:
            if not isinstance(self.freeze_ignore, list):
                server.error(
                    'Improper value for "session.freeze.ignore"!',
                )
                self.freeze_ignore = None
            else:
                for x in range(0, len(self.freeze_ignore)):
                    self.freeze_ignore[x] = eval_env(self.freeze_ignore[x]).lower()
        self.freeze_windows = boolean(
            server.get_config("session.freeze.enabled", DEFAULT_SESSION_FREEZE, True)
        )
        self.profiles["video"] = _get_profile(server, "video")
        self.profiles["rotate"] = _get_profile(server, "rotate")
        self.profiles["power_ac"] = _get_profile(server, "power_ac")
        self.profiles["lock_pre"] = _get_profile(server, "lock_pre")
        self.profiles["lock_post"] = _get_profile(server, "lock_post")
        self.profiles["suspend_pre"] = _get_profile(server, "suspend_pre")
        self.profiles["suspend_post"] = _get_profile(server, "suspend_post")
        self.profiles["power_battery"] = _get_profile(server, "power_battery")
        self.profiles["hibernate_pre"] = _get_profile(server, "hibernate_pre")
        self.profiles["hibernate_post"] = _get_profile(server, "hibernate_post")

    def thread(self, server):
        if not self.scheduler.empty():
            self.scheduler.run(blocking=False)
        elif self.switch_time is not None and self.switch_time > 0:
            self.switch_event = self.scheduler.enter(
                self.switch_time, 1, background, argument=(server,)
            )
        if self.composer is not None and self.composer.poll() is not None:
            stop(self.composer)
            self.composer = None
        if len(self.running) == 0:
            return
        for proc in list(self.running):
            if proc is not None and proc.poll() is not None:
                stop(proc)
                self.running.remove(proc)
            del proc

    def reload(self, server, message):
        if self.switch_event is not None:
            try:
                self.scheduler.cancel(self.switch_event)
            except ValueError:
                pass
            self.switch_event = None
        if self.composer is not None:
            stop(self.composer)
        for proc in self.running:
            stop(proc)
        self.running.clear()
        self.profiles.clear()
        if message.header() == HOOK_SHUTDOWN:
            return
        server.debug("Reloading configuration..")
        self.setup(server)

    def freeze(self, server, message):
        self._freeze_windows(server, message.trigger is not None)
        self._freeze_composer(server, message.trigger is not None)
        if message.trigger is not None:
            return self._trigger_profile(server, "lock_pre")
        if message.type == MESSAGE_TYPE_POST:
            return self._trigger_profile(server, "lock_post")

    def profile(self, server, message):
        if message.header() == HOOK_POWER:
            if message.type == MESSAGE_TYPE_PRE:
                return self._trigger_profile(server, "power_battery")
            if message.type == MESSAGE_TYPE_POST:
                return self._trigger_profile(server, "power_ac")
        elif message.header() == HOOK_DISPLAY:
            if (
                self.auto_monitor
                and message.get("active") == 1
                and message.get("connected", 1) > 1
            ):
                self._exec_profile_command(server, BACKGROUND_EXEC_AUTO)
            background(server)
            return self._trigger_profile(server, "video")
        elif message.header() == HOOK_ROTATE:
            return self._trigger_profile(server, "rotate")
        elif message.header() == HOOK_SUSPEND:
            if message.type == MESSAGE_TYPE_PRE:
                return self._trigger_profile(server, "suspend_pre")
            if message.type == MESSAGE_TYPE_POST:
                return self._trigger_profile(server, "suspend_post")
        elif message.header() == HOOK_HIBERNATE:
            if message.type == MESSAGE_TYPE_PRE:
                return self._trigger_profile(server, "hibernate_pre")
            if message.type == MESSAGE_TYPE_POST:
                return self._trigger_profile(server, "hibernate_post")

    def _freeze_windows(self, server, pre):
        if not self.freeze_windows:
            return server.debug("Not freezing windows, as it's disabled in config.")
        try:
            windows = run(SESSION_WINDOW_LIST, wait=True, ignore_errors=False)
        except OSError as err:
            return server.error(
                "Attempting to generate a list of windows raised an exception!",
                err=err,
            )
        v = windows.split("\n")
        del windows
        if len(v) == 0:
            return server.debug("No windows detected, not freezing.")
        for w in v:
            e = w.split()
            if len(e) < 4:
                continue
            try:
                p = int(e[2])
            except ValueError:
                continue
            if not self._can_freeze_window(e[3], p):
                server.debug(f'Not freezing ignored window PID "{p}" class "{e[3]}"".')
                del p
                continue
            if pre:
                try:
                    kill(p, SIGSTOP)
                except OSError as err:
                    server.error(
                        f'Attempting to un-freeze PID "{p}" raised an exception!',
                        err=err,
                    )
                continue
            try:
                kill(p, SIGCONT)
            except OSError as err:
                server.error(
                    f'Attempting to un-freeze PID "{p}" raised an exception!',
                    err=err,
                )
        del v

    def _freeze_composer(self, server, pre):
        if self.composer is None or self.composer.poll() is not None:
            return
        if pre:
            try:
                self.composer.send_signal(SIGSTOP)
            except OSError as err:
                server.error(
                    "Attempting to freeze the composer raised an exception!",
                    err=err,
                )
            else:
                server.debug("Freezing the composer due to lockscreen.")
            return
        try:
            self.composer.send_signal(SIGCONT)
        except OSError as err:
            server.error(
                "Attempting to un-freeze the composer raised an exception!",
                err=err,
            )
        else:
            server.debug("Unfreezing the composer due to lockscreen removal.")

    def _trigger_profile(self, server, name):
        profile = self.profiles.get(name)
        if profile is None or len(profile) == 0:
            return
        server.debug(f'Triggering profile commands for "{name}"!')
        if isinstance(profile, str):
            self._exec_profile_command(server, profile)
        elif isinstance(profile, list):
            for command in profile:
                self._exec_profile_command(server, command)

    def _can_freeze_window(self, win_class, win_pid):
        if win_pid == 0:
            return False
        if not isinstance(self.freeze_ignore, list):
            return True
        for e in self.freeze_ignore:
            if e in win_class.lower():
                return False
        return True

    def _exec_profile_command(self, server, command):
        try:
            self.running.append(
                Popen(
                    eval_env(command).split(" "),
                    stdout=DEVNULL,
                    stderr=DEVNULL,
                    env=environ,
                )
            )
        except (OSError, SubprocessError) as err:
            server.error(
                f'Starting the profile command "{command}" raised an Exception!',
                err=err,
            )
            return
        server.debug(f'Started the profile command "{command}"!')
