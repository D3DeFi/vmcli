import logging
from lib import config as conf


class Logger(object):
    """Provides wrapper for loggin.Logger object with option to set logging level across
    all existing instances of Logger class via their shared logging.Handler."""

    def __init__(self, name):
        self.formatter = logging.Formatter(conf.LOG_FORMAT)
        self.handler = self._getHandler(conf.LOG_PATH, self.formatter)
        self.logger = logging.getLogger(name)
        self.logger.addHandler(self.handler)
        self.setLevel(conf.LOG_LEVEL)
        self._quiet = False

    @staticmethod
    def _getHandler(path, formatter_class):
        """Returns appropriate logging.Handler object based on existence of path variable."""
        if path:
            handler = logging.FileHandler(path)
        else:
            handler = logging.StreamHandler()
        # Attach log format defining class to the handler
        handler.setFormatter(formatter_class)
        return handler

    def setLevel(self, lvl):
        log_level = getattr(logging, lvl, None)
        if log_level:
            self.logger.setLevel(log_level)
            self.handler.setLevel(log_level)

    def quiet(self):
        self._quiet = True

    def debug(self, *args, **kwargs):
        if not self._quiet:
            self.logger.debug(*args, **kwargs)

    def info(self, *args, **kwargs):
        if not self._quiet:
            self.logger.info(*args, **kwargs)

    def warning(self, *args, **kwargs):
        if not self._quiet:
            self.logger.warning(*args, **kwargs)

    def error(self, *args, **kwargs):
        if not self._quiet:
            self.logger.error(*args, **kwargs)

    def critical(self, *args, **kwargs):
        if not self._quiet:
            self.logger.critical(*args, **kwargs)


logger = Logger('vmcli.lib.tools.logging.Logger')
