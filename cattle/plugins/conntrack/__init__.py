from cattle.type_manager import register_type, LIFECYCLE
from .conntrack import Conntrack

register_type(LIFECYCLE, Conntrack())
