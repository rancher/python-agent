from cattle import Config
from cattle.process_manager import background


class ConsoleAgent(object):

    def on_startup(self):
        background(['nodejs',
                    Config.console_agent_main(),
                    '-d',  'http://unix:/var/run/docker.sock:',
                    '-k', Config.jwt_public_key_file(),
                    '-p', str(Config.console_agent_port())])
