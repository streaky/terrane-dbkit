#!/usr/bin/env python3
"""Own a command tree until reaped, without timing out ordinary command work.

Linux subreaping retains orphan ownership. Cancellation or direct-child exit
starts a one-second TERM grace period, followed by KILL for remaining descendants.
Cleanup mode ignores repeated terminal signals throughout stack teardown.
"""
import ctypes
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


SHUTDOWN_GRACE = 1.0


def descendants():
    """Include children forked by worker threads and detached process sessions."""
    owned = []
    pending = [os.getpid()]
    while pending:
        parent = pending.pop()
        try:
            tasks = list(Path(f"/proc/{parent}/task").iterdir())
        except FileNotFoundError:
            continue
        for task in tasks:
            try:
                children = (task / "children").read_text().split()
            except FileNotFoundError:
                continue
            for text in children:
                pid = int(text)
                owned.append(pid)
                pending.append(pid)
    return owned


def main():
    command = sys.argv[1:]
    cleanup = bool(command and command[0] == "--cleanup")
    if cleanup:
        command = command[1:]
    if not command:
        raise SystemExit("run_owned.py requires a command")
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))

    terminating = False

    def terminate(_signum, _frame):
        nonlocal terminating
        terminating = True

    for number in (signal.SIGINT, signal.SIGTERM):
        signal.signal(number, signal.SIG_IGN if cleanup else terminate)
    child = subprocess.Popen(command, start_new_session=True)
    status = None
    deadline = None
    terminated = set()
    killed = set()
    while True:
        no_children = False
        while True:
            try:
                pid, result = os.waitpid(-1, os.WNOHANG)
            except ChildProcessError:
                no_children = True
                break
            if pid == 0:
                break
            if pid == child.pid:
                status = os.waitstatus_to_exitcode(result)
                child.returncode = status
        if no_children:
            break
        if terminating or status is not None:
            if deadline is None:
                deadline = time.monotonic() + SHUTDOWN_GRACE
            force = time.monotonic() >= deadline
            signalled = killed if force else terminated
            # Signal leaves before parents, preserving ownership until subreaping
            # adopts any survivors. Re-scan for children forked during shutdown.
            for pid in reversed(descendants()):
                if pid not in signalled:
                    try:
                        os.kill(pid, signal.SIGKILL if force else signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                    signalled.add(pid)
        time.sleep(0.01)
    if terminating:
        return 143
    if status is None:
        raise RuntimeError("owned command was not reaped")
    return status if status >= 0 else 128 - status


if __name__ == "__main__":
    sys.exit(main())
