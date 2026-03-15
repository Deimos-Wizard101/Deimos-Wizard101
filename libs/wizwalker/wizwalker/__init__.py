import logging

from loguru import logger

from .constants import *
from .errors import *
from .utils import XYZ, Orient, Rectangle
from . import combat, memory, utils
from .file_readers import CacheHandler, NifMap, Wad
from .mouse_handler import MouseHandler
from .client import Client
from .client_handler import ClientHandler
from .hotkey import *

logger.disable("wizwalker")
logging.getLogger("pymem").setLevel(logging.FATAL)
