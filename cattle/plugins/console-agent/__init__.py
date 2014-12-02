from cattle.type_manager import register_type, LIFECYCLE

from .console_agent import ConsoleAgent

register_type(LIFECYCLE, ConsoleAgent())
