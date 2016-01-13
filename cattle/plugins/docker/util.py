import logging
import os

from docker.errors import APIError

log = logging.getLogger('docker')


_NET_UTIL = os.path.join(os.path.dirname(__file__), 'net-util.sh')


def pipe_error(ctx, stderr, buffer):
    for line in stderr:
        if len(line) > 0:
            buffer.append(line)
            log.error('[%s] %s', ctx, line[:-1])


def sudo(args):
    if os.getuid() == 0:
        return args
    return ['sudo'] + args


def add_to_env(config, *args, **kw):
    try:
        env = config['environment']
    except KeyError:
        env = {}
        config['environment'] = env

    for i in range(0, len(args), 2):
        if args[i] not in env:
            env[args[i]] = args[i+1]

    for k, v in kw.items():
        if k not in env:
            env[k] = v


def add_label(config, new_labels):
    try:
        labels = config['labels']
    except KeyError:
        labels = {}
        config['labels'] = labels

    labels.update(new_labels)


def is_nonrancher_container(instance):
    try:
        return instance.nativeContainer
    except (KeyError, AttributeError):
        return False


def is_no_op(resource):
    try:
        return resource.processData.containerNoOpEvent
    except (AttributeError, KeyError):
        return False


def remove_container(client, container):
    try:
        client.remove_container(container, force=True, v=True)
    except APIError as e:
        try:
            if e.response.status_code != 404:
                raise e
        except AttributeError:
            raise e
