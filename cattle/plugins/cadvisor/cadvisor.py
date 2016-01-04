import logging
import os
import shlex

from cattle import Config
from cattle.process_manager import background

log = logging.getLogger('cadvisor')


class Cadvisor(object):

    def on_startup(self):
        cmd = ['cadvisor',
               '-logtostderr=true',
               '-listen_ip', Config.cadvisor_ip(),
               '-port', str(Config.cadvisor_port()),
               '-housekeeping_interval', Config.cadvisor_interval()]

        docker_root = Config.cadvisor_docker_root()
        if docker_root:
            cmd += ["-docker_root", docker_root]

        cadvisor_opts = Config.cadvisor_opts()
        if cadvisor_opts:
            try:
                cmd += shlex.split(cadvisor_opts)
            except ValueError:
                log.exception(
                    "Error missing closing `'` in: {0}".format(cadvisor_opts))
                pass

        wrapper = Config.cadvisor_wrapper()

        if len(wrapper):
            cmd.insert(0, wrapper)
        else:
            if os.path.exists('/host/proc/1/ns/mnt'):
                cmd = ['nsenter', '--mount=/host/proc/1/ns/mnt', '--'] + cmd

        background(cmd)
