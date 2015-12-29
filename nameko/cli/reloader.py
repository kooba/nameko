import os
import subprocess
import sys
import time
import logging
import threading
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from werkzeug._compat import PY2, iteritems, text_type
from werkzeug._internal import _log


class CustomHandler(FileSystemEventHandler):

    def on_created(self, event):
        print(event.src_path)
        self.reload()

    def on_modified(self, event):
        print(event.src_path)
        self.reload()

    def on_moved(self, event):
        print(event.src_path)
        print(event.dest_path)
        self.reload()

    def on_deleted(self, event):
        print(event.src_path)
        self.reload()

    def reload(self):
        print('Reloading')


def run_reloader(run, service_runner):

    path = '/Users/jakubborys/Dropbox/OslDev/OSL/nameko/docs/examples'
    t = threading.Thread(target=run, args=())
    t.setDaemon(True)
    t.start()

    event_handler = CustomHandler(run, service_runner)
    observer = Observer()
    observer.schedule(event_handler, path, recursive=True)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


def run_rel():
    reloader = WatchdogReloaderLoop()
    reloader.run()


#
# if __name__ == "__main__":
#     logging.basicConfig(level=logging.INFO,
#                         format='%(asctime)s - %(message)s',
#                         datefmt='%Y-%m-%d %H:%M:%S')
#     path = '/Users/jakubborys/Dropbox/OslDev/OSL/nameko/docs/examples' #sys.argv[1] if len(sys.argv) > 1 else '.'
#     event_handler = CustomHandler()
#     observer = Observer()
#     import pdb; pdb.set_trace();
#     observer.schedule(event_handler, path, recursive=True)
#     observer.start()
#     try:
#         while True:
#             time.sleep(1)
#     except KeyboardInterrupt:
#         observer.stop()
#     observer.join()


def _find_observable_paths(extra_files=None):
    """Finds all paths that should be observed."""
    rv = set(os.path.abspath(x) for x in sys.path)

    for filename in extra_files or ():
        rv.add(os.path.dirname(os.path.abspath(filename)))

    for module in list(sys.modules.values()):
        fn = getattr(module, '__file__', None)
        if fn is None:
            continue
        fn = os.path.abspath(fn)
        rv.add(os.path.dirname(fn))

    return _find_common_roots(rv)


def _find_common_roots(paths):
    """Out of some paths it finds the common roots that need monitoring."""
    paths = [x.split(os.path.sep) for x in paths]
    root = {}
    for chunks in sorted(paths, key=len, reverse=True):
        node = root
        for chunk in chunks:
            node = node.setdefault(chunk, {})
        node.clear()

    rv = set()

    def _walk(node, path):
        for prefix, child in iteritems(node):
            _walk(child, path + (prefix,))
        if not node:
            rv.add('/'.join(path))
    _walk(root, ())
    return rv

class ReloaderLoop(object):
    name = None

    # monkeypatched by testsuite. wrapping with `staticmethod` is required in
    # case time.sleep has been replaced by a non-c function (e.g. by
    # `eventlet.monkey_patch`) before we get here
    _sleep = staticmethod(time.sleep)

    def __init__(self, extra_files=None, interval=1):
        self.extra_files = set(os.path.abspath(x)
                               for x in extra_files or ())
        self.interval = interval

    def run(self):
        pass

    def restart_with_reloader(self):
        """Spawn a new Python interpreter with the same arguments as this one,
        but running the reloader thread.
        """
        while 1:
            _log('info', ' * Restarting with %s' % self.name)
            args = [sys.executable] + sys.argv
            new_environ = os.environ.copy()
            new_environ['WERKZEUG_RUN_MAIN'] = 'true'

            # a weird bug on windows. sometimes unicode strings end up in the
            # environment and subprocess.call does not like this, encode them
            # to latin1 and continue.
            if os.name == 'nt' and PY2:
                for key, value in iteritems(new_environ):
                    if isinstance(value, text_type):
                        new_environ[key] = value.encode('iso-8859-1')

            exit_code = subprocess.call(args, env=new_environ,
                                        close_fds=False)
            if exit_code != 3:
                return exit_code

    def trigger_reload(self, filename):
        self.log_reload(filename)
        sys.exit(3)

    def log_reload(self, filename):
        filename = os.path.abspath(filename)
        _log('info', ' * Detected change in %r, reloading' % filename)


class WatchdogReloaderLoop(ReloaderLoop):

    def __init__(self, *args, **kwargs):
        ReloaderLoop.__init__(self, *args, **kwargs)
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
        self.observable_paths = set()

        def _check_modification(filename):
            if filename in self.extra_files:
                self.trigger_reload(filename)
                dirname = os.path.dirname(filename)
            if dirname.startswith(tuple(self.observable_paths)):
                if filename.endswith(('.pyc', '.pyo')):
                    self.trigger_reload(filename[:-1])
                elif filename.endswith('.py'):
                    self.trigger_reload(filename)

        class _CustomHandler(FileSystemEventHandler):

            def on_created(self, event):
                _check_modification(event.src_path)

            def on_modified(self, event):
                _check_modification(event.src_path)

            def on_moved(self, event):
                _check_modification(event.src_path)
                _check_modification(event.dest_path)

            def on_deleted(self, event):
                _check_modification(event.src_path)

        reloader_name = Observer.__name__.lower()
        if reloader_name.endswith('observer'):
            reloader_name = reloader_name[:-8]
        reloader_name += ' reloader'

        self.name = reloader_name

        self.observer_class = Observer
        self.event_handler = _CustomHandler()
        self.should_reload = False

    def trigger_reload(self, filename):
        # This is called inside an event handler, which means throwing
        # SystemExit has no effect.
        # https://github.com/gorakhargosh/watchdog/issues/294
        self.should_reload = True
        self.log_reload(filename)

    def run(self):
        watches = {}
        observer = self.observer_class()
        observer.start()

        while not self.should_reload:
            to_delete = set(watches)
            paths = ['/Users/jakubborys/Dropbox/OslDev/OSL/nameko/docs/examples']#_find_observable_paths(self.extra_files)
            for path in paths:
                if path not in watches:
                    try:
                        print("starting")
                        watches[path] = observer.schedule(
                            self.event_handler, path, recursive=False)
                        print("done")
                    except OSError:
                        # Clear this path from list of watches We don't want
                        # the same error message showing again in the next
                        # iteration.

                        watches[path] = None
                to_delete.discard(path)
            for path in to_delete:
                watch = watches.pop(path, None)
                if watch is not None:
                    observer.unschedule(watch)

            self.observable_paths = paths
            self._sleep(self.interval)

        sys.exit(3)


def run_with_reloader(main_func):
    """Run the given function in an independent python interpreter."""
    import signal
    # reloader = WatchdogReloaderLoop()
    reloader = WatchdogReloaderNew()
    signal.signal(signal.SIGTERM, lambda *args: sys.exit(0))
    try:
        if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
            t = threading.Thread(target=main_func, args=())
            t.setDaemon(True)
            t.start()
            reloader.run()
        else:
            sys.exit(reloader.restart_with_reloader())
    except KeyboardInterrupt:
        pass


def print_something():
    print("Someging changed reloading")


# if __name__ == "__main__":
#     run_with_reloader(print_something)


class WatchdogReloaderNew():

    def restart_with_reloader(self):
        """Spawn a new Python interpreter with the same arguments as this one,
        but running the reloader thread.
        """
        while 1:
            _log('info', ' * Restarting')
            args = [sys.executable] + sys.argv
            new_environ = os.environ.copy()
            new_environ['WERKZEUG_RUN_MAIN'] = 'true'

            exit_code = subprocess.call(args, env=new_environ,
                                        close_fds=False)
            if exit_code != 3:
                return exit_code

    def run(self):
        start = 0

        while not start > 5:
            start += 1
            time.sleep(1)

        print("exiting")
        sys.exit(3)
