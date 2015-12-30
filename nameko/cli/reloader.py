import os
import subprocess
import sys
import time
from logging import getLogger
import threading

_log = getLogger(__name__)

# monkeypatched by testsuite. wrapping with `staticmethod` is required in
# case time.sleep has been replaced by a non-c function (e.g. by
# `eventlet.monkey_patch`) before we get here
_sleep = staticmethod(time.sleep)


def _get_module_files():
    """This iterates over all relevant Python files.  It goes through all
    loaded files from modules, all files in folders of already loaded modules
    as well as all files reachable through a package.
    """
    # The list call is necessary on Python 3 in case the module
    # dictionary modifies during iteration.
    for module in list(sys.modules.values()):
        if module is None:
            continue
        filename = getattr(module, '__file__', None)
        if filename:
            while not os.path.isfile(filename):
                old = filename
                filename = os.path.dirname(filename)
                if filename == old:
                    break
            else:
                if filename[-4:] in ('.pyc', '.pyo'):
                    filename = filename[:-1]
                yield filename


def restart_with_reloader():
    """Spawn a new Python interpreter with the same arguments as this one,
    but running the reloader thread.
    """
    while True:
        _log.info('Restarting with reloader')
        args = [sys.executable] + sys.argv
        new_environ = os.environ.copy()
        new_environ['NAMEKO_RUN'] = 'true'

        exit_code = subprocess.call(args, env=new_environ,
                                    close_fds=False)
        if exit_code != 3:
            return exit_code


def trigger_reload(filename):
    log_reload(filename)
    sys.exit(3)


def log_reload(filename):
    filename = os.path.abspath(filename)
    _log.info('Detected change in {}, reloading'.format(filename))


def watch_files():
    mtimes = {}
    while True:
        for filename in _get_module_files():
            try:
                mtime = os.stat(filename).st_mtime
            except OSError:
                continue

            old_time = mtimes.get(filename)
            if old_time is None:
                mtimes[filename] = mtime
                continue
            elif mtime > old_time:
                trigger_reload(filename)
        time.sleep(1)


def run_with_reloader(main_func):
    """Run the given function in an independent python interpreter."""
    import signal

    signal.signal(signal.SIGTERM, lambda *args: sys.exit(0))
    try:
        if os.environ.get('NAMEKO_RUN') == 'true':
            t = threading.Thread(target=main_func, args=())
            t.setDaemon(True)
            t.start()
            watch_files()
        else:
            sys.exit(restart_with_reloader())
    except KeyboardInterrupt:
        pass
