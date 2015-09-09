import logging

from cattle import Config
from cattle.utils import reply, popen
from .compute import DockerCompute
from cattle.agent.handler import BaseHandler
from cattle.progress import Progress
from cattle.type_manager import get_type, MARSHALLER
from . import docker_client

import subprocess
import os
import time

log = logging.getLogger('docker')


def ns_exec(pid, event):
    script = os.path.join(Config.home(), 'events', event.name.split(';')[0])
    cmd = ['nsenter',
           '-F',
           '-m',
           '-u',
           '-i',
           '-n',
           '-p',
           '-t', str(pid),
           '--', script]

    marshaller = get_type(MARSHALLER)
    input = marshaller.to_string(event)
    data = None

    env = {}
    with open('/proc/{}/environ'.format(pid)) as f:
        for line in f.read().split('\0'):
            if not len(line):
                continue
            kv = line.split('=', 1)
            if kv[0].startswith('CATTLE'):
                env[kv[0]] = kv[1]

    env['PATH'] = os.environ['PATH']
    env['CATTLE_CONFIG_URL'] = Config.config_url()

    for i in range(3):
        p = popen(cmd,
                  env=env,
                  stdin=subprocess.PIPE,
                  stdout=subprocess.PIPE,
                  stderr=subprocess.STDOUT)
        output, error = p.communicate(input=input)
        retcode = p.poll()

        if retcode == 0:
            break

        exists_cmd = cmd[:-1] + ['/usr/bin/test', '-e', script]
        if popen(exists_cmd, env=env).wait() == 0:
            break

        # Sleep and try again if missing
        time.sleep(1)

    if retcode:
        return retcode, output, None

    text = []
    for line in output.splitlines():
        if line.startswith('{'):
            data = marshaller.from_string(line)
            break
        text.append(line)

    return retcode, ''.join(text), data


class DockerDelegate(BaseHandler):
    def __init__(self):
        self.compute = DockerCompute()
        pass

    def events(self):
        return ['delegate.request']

    def delegate_request(self, req=None, event=None, instanceData=None, **kw):
        if instanceData.kind != 'container' or \
           instanceData.get('token') is None:
            return

        container = self.compute.get_container(docker_client(), instanceData)
        if container is None:
            log.info('Can not call [%s], container does not exists',
                     instanceData.uuid)
            return

        inspect = self.compute.inspect(container)

        try:
            running = inspect['State']['Running']
            if not running:
                log.error('Can not call [%s], container is not running',
                          instanceData.uuid)
                return
        except KeyError:
            log.error('Can not call [%s], container is not running',
                      instanceData.uuid)
            return

        progress = Progress(event, parent=req)
        exit_code, output, data = ns_exec(inspect['State']['Pid'], event)

        if exit_code == 0:
            return reply(event, data, parent=req)
        else:
            progress.update('Update failed', data={
                'exitCode': exit_code,
                'output': output
            })
