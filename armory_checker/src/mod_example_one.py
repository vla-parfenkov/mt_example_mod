import logging


from gui.mods.armory_checker.armory_checker import g_ACService

_logger = logging.getLogger(__name__)


def init():
    g_ACService.init()


def fini():
    g_ACService.fini()
