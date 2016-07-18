import eventlet
import os
import signal
import subprocess
import sys
import time
from logging import getLogger
from eventlet import event

_log = getLogger(__name__)


def stop():
    sys.exit(0)


def run_with_reloader(main_func, *args, **kwargs):
    """
    Run the given function with reloader.

    :param main_func:
        Function to run in an independent python interpreter.
    """

    # catch TERM signal to allow finalizers to run and reap daemonic children
    # signal.signal(signal.SIGTERM, lambda *args: sys.exit(0))
    signal.signal(signal.SIGTERM, stop)

    reload_event = event.Event()

    kwargs['reload_event'] = reload_event

    try:
        if os.environ.get('NAMEKO_RUN') == 'true':
            main_gt = eventlet.spawn(main_func, *args, **kwargs)
            eventlet.spawn(watch_files, reload_event)
            main_gt.wait()
            sys.exit(3)
        else:
            sys.exit(restart_with_reloader())
    except KeyboardInterrupt:
        pass


def restart_with_reloader():
    """Spawn a new Python interpreter with the same arguments as this one,
    but running the reloader thread.
    """
    while True:
        _log.info('Starting with reloader')
        args = [sys.executable] + sys.argv
        new_environ = os.environ.copy()
        new_environ['NAMEKO_RUN'] = 'true'

        exit_code = subprocess.call(args, env=new_environ, close_fds=False)

        if exit_code != 3:
            return exit_code


def trigger_reload(filename, reload_event):
    log_reload(filename)
    reload_event.send()


def log_reload(filename):
    filename = os.path.abspath(filename)
    _log.info('Detected change in {}, reloading'.format(filename))


def watch_files(reload_event):
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
                trigger_reload(filename, reload_event)
        time.sleep(1)


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
