"""Exercise the real runner with isolated command stand-ins, never Docker data."""
from pathlib import Path
import fcntl
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest


TESTS = Path(__file__).resolve().parent
STANDIN = r'''#!/usr/bin/env python3
from pathlib import Path
import os
import signal
import subprocess
import sys
import time

root = Path(os.environ['RUNNER_PROBE'])
name = Path(sys.argv[0]).name
if name == 'docker':
    phase = next((part for part in ('down', 'up', 'port') if part in sys.argv), 'reset')
else:
    phase = 'compiler' if name == 'compiler' else 'suite'
with (root / 'events').open('a') as output:
    output.write(phase + '\n')
if phase == 'reset':
    state = root / 'package/tests/.state/postgres'
    for item in state.iterdir():
        if item.is_dir():
            import shutil
            shutil.rmtree(item)
        else:
            item.unlink()
if phase == 'up':
    if (root / 'package/tests/.state/postgres/inspection').exists():
        raise SystemExit('reset did not precede up')
if phase == 'suite':
    (root / 'package/tests/.state/postgres/inspection').write_text('generated')
    if os.environ.get('FAIL_SUITE'):
        sys.exit(19)
if phase == 'down' and os.environ.get('BLOCK_CLEANUP') and 'up' in (root / 'events').read_text().splitlines():
    (root / 'cleanup-ready').write_text(str(os.getpid()))
    while not (root / 'cleanup-release').exists():
        time.sleep(0.01)
    with (root / 'events').open('a') as output:
        output.write('cleanup-finished\n')
if phase == 'down' and os.environ.get('STUBBORN') and (root / 'ready').exists():
    try:
        os.kill(int((root / 'ready').read_text()), 0)
    except ProcessLookupError:
        pass
    else:
        raise SystemExit('cleanup started before descendant reaping')
if phase == 'down' and os.environ.get('FAIL_STOP'):
    sys.exit(11)
if phase == os.environ.get('BLOCK_PHASE'):
    if os.environ.get('STUBBORN'):
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    subprocess.Popen([sys.executable, str(root / 'descendant.py')],
                     start_new_session=bool(os.environ.get('DETACHED')))
    while not (root / 'ready').exists():
        time.sleep(0.01)
    if os.environ.get('BLOCK_MODE') == 'normal-exit':
        sys.exit(0)
    while True:
        time.sleep(1)
if phase == 'port':
    print('127.0.0.1:5432')
if phase == 'compiler':
    sys.exit(int(os.environ.get('COMPILER_EXIT', '0')))
'''
DESCENDANT = r'''from pathlib import Path
import fcntl
import os
import signal
import time

root = Path(os.environ['RUNNER_PROBE'])
def terminate(_signal, _frame):
    time.sleep(0.2)
    with (root / 'package/tests/.state/postgres-test.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            state = 'lock-released-early'
        except BlockingIOError:
            state = 'lock-held'
    with (root / 'events').open('a') as output:
        output.write(state + '\ndescendant-finished\n')
    raise SystemExit(0)
signal.signal(signal.SIGTERM, signal.SIG_IGN if os.environ.get('STUBBORN') else terminate)
(root / 'ready').write_text(str(os.getpid()))
while True:
    time.sleep(1)
'''


class RunnerLifecycle(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='dbkit-runner-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.tests = self.root / 'package/tests'
        self.tests.mkdir(parents=True)
        (self.root / 'bin').mkdir()
        for name in ('run_tests.sh', 'run_owned.py'):
            shutil.copy2(TESTS / name, self.tests / name)
        for path in (self.root / 'bin/docker', self.root / 'compiler',
                     self.tests / 'test_database.py', self.tests / 'test_postgres.py'):
            path.write_text(STANDIN)
            path.chmod(0o755)
        (self.root / 'descendant.py').write_text(DESCENDANT)
        self.environment = dict(os.environ, RUNNER_PROBE=str(self.root),
                                PATH=str(self.root / 'bin') + ':' + os.environ['PATH'])
        self.command = ['bash', str(self.tests / 'run_tests.sh'),
                        '--terrane', str(self.root / 'compiler')]

    def events(self):
        return (self.root / 'events').read_text().splitlines()

    def test_reset_and_inspection_retention(self):
        for environment, expected in (({}, 0), ({'FAIL_SUITE': '1'}, 19)):
            with self.subTest(environment=environment):
                (self.root / 'events').unlink(missing_ok=True)
                state = self.tests / '.state/postgres'
                state.mkdir(parents=True, exist_ok=True)
                sentinel = state / 'inspection'
                sentinel.write_text('pre-run')
                result = subprocess.run(self.command, env=dict(self.environment, **environment),
                                        capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, expected, result.stderr)
                self.assertEqual((state / 'inspection').read_text(), 'generated')
                events = self.events()
                self.assertLess(events.index('reset'), events.index('up'))
                self.assertLess(events.index('suite'), len(events) - 1)
                self.assertNotIn('reset', events[events.index('suite') + 1:])

    def test_failed_initial_stop_prevents_reset(self):
        result = subprocess.run(self.command, env=dict(self.environment, FAIL_STOP='1'),
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 11, result.stderr)
        self.assertNotIn('reset', self.events())
        self.assertNotIn('up', self.events())

    def test_pid_signals_reap_descendants_before_cleanup_and_unlock(self):
        for phase in ('compiler', 'port'):
            for number, expected in ((signal.SIGTERM, 143), (signal.SIGINT, 130)):
                with self.subTest(phase=phase, signal=number):
                    (self.root / 'ready').unlink(missing_ok=True)
                    (self.root / 'events').unlink(missing_ok=True)
                    process = subprocess.Popen(self.command,
                                               env=dict(self.environment, BLOCK_PHASE=phase),
                                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                               text=True, start_new_session=True)
                    try:
                        deadline = time.monotonic() + 5
                        while not (self.root / 'ready').exists() and time.monotonic() < deadline:
                            if process.poll() is not None:
                                break
                            time.sleep(0.01)
                        self.assertTrue((self.root / 'ready').exists(), 'owned descendant did not start')
                        descendant = int((self.root / 'ready').read_text())
                        process.send_signal(number)
                        _, stderr = process.communicate(timeout=5)
                        self.assertEqual(process.returncode, expected, stderr)
                        events = self.events()
                        self.assertIn('lock-held', events)
                        self.assertNotIn('lock-released-early', events)
                        self.assertEqual(events[-2:], ['descendant-finished', 'down'])
                        with self.assertRaises(ProcessLookupError):
                            os.kill(descendant, 0)
                        with (self.tests / '.state/postgres-test.lock').open('w') as lock:
                            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    finally:
                        if process.poll() is None:
                            os.killpg(process.pid, signal.SIGTERM)
                            process.communicate(timeout=5)

    def wait_ready(self, process, name):
        marker = self.root / name
        deadline = time.monotonic() + 5
        while not marker.exists() and time.monotonic() < deadline and process.poll() is None:
            time.sleep(0.01)
        self.assertTrue(marker.exists(), f'{name} was not reached')
        return int(marker.read_text())

    def test_stubborn_descendants_are_bounded_after_cancel_or_parent_exit(self):
        for mode in ('cancel', 'normal-exit'):
            with self.subTest(mode=mode):
                (self.root / 'ready').unlink(missing_ok=True)
                (self.root / 'events').unlink(missing_ok=True)
                process = subprocess.Popen(
                    self.command,
                    env=dict(self.environment, BLOCK_PHASE='compiler', BLOCK_MODE=mode,
                             STUBBORN='1', DETACHED='1'),
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                    start_new_session=True)
                try:
                    descendant = self.wait_ready(process, 'ready')
                    if mode == 'cancel':
                        process.send_signal(signal.SIGTERM)
                    _, stderr = process.communicate(timeout=5)
                    self.assertEqual(process.returncode, 143 if mode == 'cancel' else 0, stderr)
                    self.assertNotIn('cleanup started before descendant reaping', stderr)
                    with self.assertRaises(ProcessLookupError):
                        os.kill(descendant, 0)
                    with (self.tests / '.state/postgres-test.lock').open('w') as lock:
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                finally:
                    if process.poll() is None:
                        process.send_signal(signal.SIGTERM)
                        process.communicate(timeout=5)

    def test_repeated_group_signals_do_not_interrupt_cleanup(self):
        process = subprocess.Popen(
            self.command, env=dict(self.environment, BLOCK_CLEANUP='1'),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
        try:
            cleanup_pid = self.wait_ready(process, 'cleanup-ready')
            for number in (signal.SIGINT, signal.SIGINT, signal.SIGTERM):
                os.killpg(process.pid, number)
                time.sleep(0.03)
            self.assertIsNone(process.poll())
            with (self.tests / '.state/postgres-test.lock').open('w') as lock:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            (self.root / 'cleanup-release').touch()
            _, stderr = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 0, stderr)
            self.assertEqual(self.events()[-1], 'cleanup-finished')
            with self.assertRaises(ProcessLookupError):
                os.kill(cleanup_pid, 0)
        finally:
            (self.root / 'cleanup-release').touch()
            if process.poll() is None:
                process.communicate(timeout=5)

    def test_live_command_is_not_subject_to_shutdown_deadline(self):
        result = subprocess.run(
            [sys.executable, str(self.tests / 'run_owned.py'), sys.executable, '-c',
             'import time; time.sleep(1.4); raise SystemExit(9)'],
            capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 9, result.stderr)


if __name__ == '__main__':
    unittest.main()
