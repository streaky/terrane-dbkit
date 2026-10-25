#!/usr/bin/env python3
"""Run one command, forwarding termination and reaping its entire child tree.

The Linux subreaper owns descendants orphaned when a command exits before its
children. The shell retains the checkout lock until this helper has reaped them.
"""
import ctypes
import os
import signal
import subprocess
import sys


def main():
    if len(sys.argv) < 2:
        raise SystemExit("run_owned.py requires a command")
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))

    child = None
    terminating = False

    def terminate(_signum, _frame):
        nonlocal terminating
        terminating = True
        if child is not None:
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

    signal.signal(signal.SIGINT, terminate)
    signal.signal(signal.SIGTERM, terminate)
    child = subprocess.Popen(sys.argv[1:], start_new_session=True)
    if terminating:
        terminate(signal.SIGTERM, None)

    status = None
    while True:
        try:
            pid, result = os.waitpid(-1, 0)
        except ChildProcessError:
            break
        if pid == child.pid:
            status = os.waitstatus_to_exitcode(result)
            child.returncode = status
    if terminating:
        return 143
    if status is None:
        raise RuntimeError("owned command was not reaped")
    return status if status >= 0 else 128 - status


if __name__ == "__main__":
    sys.exit(main())
