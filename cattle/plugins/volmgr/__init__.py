from cattle.type_manager import register_type, LIFECYCLE, REQUEST_HANDLER

from .volmgr import Volmgr
from .handler import SnapshotHandler

register_type(LIFECYCLE, Volmgr())
register_type(REQUEST_HANDLER, SnapshotHandler())
