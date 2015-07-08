import os

from cattle.process_manager import background


class Conntrack(object):

    def on_startup(self):
        script = os.path.join(os.path.dirname(__file__), 'conntrack.sh')
        background([script])
