from cattle.plugins.docker import docker_client

# TODO cattle.plugins.load_plugins() somehow make cattle.plugin.* modules
# unavailable, importing it first
import cattle.plugins.docker  # NOQA

import os
from os import path
import pytest
from cattle import CONFIG_OVERRIDE, Config
from .common_fixtures import TEST_DIR

CONFIG_OVERRIDE['DOCKER_REQUIRED'] = 'false'  # NOQA
CONFIG_OVERRIDE['DOCKER_HOST_IP'] = '1.2.3.4'  # NOQA

from datadiff.tools import assert_equals

from .response_holder import ResponseHolder
from cattle import type_manager
from cattle.agent import Agent
from cattle.utils import JsonObject

if_docker = pytest.mark.skipif('os.environ.get("DOCKER_TEST") == "false"',
                               reason='DOCKER_TEST is not set')


@pytest.fixture(scope="module")
def responses():
    r = ResponseHolder()
    type_manager.register_type(type_manager.PUBLISHER, r)
    return r


@pytest.fixture(scope="module")
def agent(responses):
    return Agent()


def json_data(name):
    marshaller = type_manager.get_type(type_manager.MARSHALLER)
    with open(os.path.join(TEST_DIR, name)) as f:
        return marshaller.from_string(f.read())


def diff_dict(left, right):
    for k in left.keys():
        left_value = left.get(k)
        right_value = right.get(k)
        try:
            diff_dict(dict(left_value), dict(right_value))
            assert_equals(dict(left_value), dict(right_value))
        except AssertionError, e:
            raise e
        except:
            pass


def event_test(agent, name, pre_func=None, post_func=None, no_diff=False):
    req = json_data(name)
    resp_valid = json_data(name + '_resp')

    if pre_func is not None:
        pre_func(req)

    resp = agent.execute(req)
    if post_func is not None:
        post_func(req, resp)

    if not no_diff:
        del resp["id"]
        del resp["time"]

        diff_dict(JsonObject.unwrap(resp_valid), JsonObject.unwrap(resp))
        assert_equals(JsonObject.unwrap(resp_valid), JsonObject.unwrap(resp))

    return req, resp


def instance_only_activate(agent, responses):
    delete_container('/c861f990-4472-4fa1-960f-65171b544c28')

    def pre(req):
        instance = req['data']['instanceHostMap']['instance']
        for nic in instance['nics']:
            nic['macAddress'] = ''

    def post(req, resp):
        docker_inspect = resp['data']['instanceHostMap']['instance']['+data'][
            'dockerInspect']
        labels = docker_inspect['Config']['Labels']
        ip = req['data']['instanceHostMap']['instance']['nics'][
            0]['ipAddresses'][0]
        expected_ip = "{0}/{1}".format(ip.address, ip.subnet.cidrSize)
        assert labels['io.rancher.container.ip'] == expected_ip
        instance_activate_common_validation(resp)

    event_test(agent, 'docker/instance_activate', pre_func=pre, post_func=post)


def state_file_exists(docker_id):
    try:
        cont_dir = Config.container_state_dir()
        file_path = path.join(cont_dir, docker_id)
        return os.path.exists(file_path)
    except:
        return False


def remove_state_file(container):
    if container:
        try:
            cont_dir = Config.container_state_dir()
            file_path = path.join(cont_dir, container['Id'])
            if os.path.exists(file_path):
                os.remove(file_path)
        except:
            pass


def delete_container(name):
    client = docker_client()
    for c in client.containers(all=True):
        for container_name in c['Names']:
            if name == container_name:
                try:
                    client.kill(c)
                except:
                    pass
                client.remove_container(c)
                remove_state_file(c)


def get_container(name):
    client = docker_client()
    for c in client.containers(all=True):
        for container_name in c['Names']:
            if name == container_name:
                return c
    return None


def instance_activate_common_validation(resp):
    docker_container = resp['data']['instanceHostMap']['instance']
    docker_container = docker_container['+data']['dockerContainer']
    docker_id = docker_container['Id']
    container_field_test_boiler_plate(resp)
    fields = resp['data']['instanceHostMap']['instance']['+data']['+fields']
    del docker_container['Ports'][0]['PublicPort']
    del docker_container['Ports'][1]['PublicPort']
    assert fields['dockerPorts']['8080/tcp'] is not None
    assert fields['dockerPorts']['12201/udp'] is not None
    fields['dockerPorts']['8080/tcp'] = '1234'
    fields['dockerPorts']['12201/udp'] = '5678'
    assert state_file_exists(docker_id)


def container_field_test_boiler_plate(resp):
    instance_data = resp['data']['instanceHostMap']['instance']['+data']
    docker_container = instance_data['dockerContainer']
    assert resp['data']['instanceHostMap']['instance']['externalId'] == \
        instance_data['dockerInspect']['Id']
    del resp['data']['instanceHostMap']['instance']['externalId']
    del instance_data['dockerInspect']
    fields = instance_data['+fields']
    del docker_container['Created']
    del docker_container['Id']
    del docker_container['Status']
    del fields['dockerIp']
    _sort_ports(docker_container)


def _sort_ports(docker_container):
    docker_container['Ports'] = sorted(docker_container['Ports'],
                                       key=lambda x: 1-x['PrivatePort'])
    return docker_container
