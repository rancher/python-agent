import json
from docker.errors import APIError
from cattle.plugins.docker import docker_client

# TODO cattle.plugins.load_plugins() somehow make cattle.plugin.* modules
# unavailable, importing it first
import cattle.plugins.docker  # NOQA

from cattle.plugins.docker.network import setup_mac_and_ip

from cattle.plugins.host_info.main import HostInfo
from .common_fixtures import *  # NOQA
import mock
import pytest
import time
from cattle import CONFIG_OVERRIDE, Config
from cattle.plugins.volmgr import volmgr, service, Volmgr

from os import path
import os

if_docker = pytest.mark.skipif('os.environ.get("DOCKER_TEST") == "false"',
                               reason='DOCKER_TEST is not set')

CONFIG_OVERRIDE['DOCKER_HOST_IP'] = '1.2.3.4'


def _state_file_exists(docker_id):
    try:
        cont_dir = Config.container_state_dir()
        file_path = path.join(cont_dir, docker_id)
        return os.path.exists(file_path)
    except:
        return False


def _remove_state_file(container):
    if container:
        try:
            cont_dir = Config.container_state_dir()
            file_path = path.join(cont_dir, container['Id'])
            if os.path.exists(file_path):
                os.remove(file_path)
        except:
            pass


def _delete_container(name):
    client = docker_client()
    for c in client.containers(all=True):
        for container_name in c['Names']:
            if name == container_name:
                try:
                    client.kill(c)
                except:
                    pass
                client.remove_container(c)
                _remove_state_file(c)


def _get_container(name):
    client = docker_client()
    for c in client.containers(all=True):
        for container_name in c['Names']:
            if name == container_name:
                return c
    return None


@if_docker
def test_image_list():
    c = docker_client()
    images = c.images(all=True)
    if len(images) == 0:
        c.pull('busybox')

    images = c.images(all=True)

    assert 'Id' in images[0]
    assert 'ID' not in images[0]


@if_docker
def test_image_activate(agent, responses):
    try:
        docker_client().remove_image('ibuildthecloud/helloworld:latest')
    except APIError:
        pass

    def post(req, resp):
        image_data = resp['data']['imageStoragePoolMap']['+data']
        del image_data['dockerImage']['VirtualSize']

    event_test(agent, 'docker/image_activate', post_func=post)


@if_docker
def test_volume_activate(agent, responses):
    event_test(agent, 'docker/volume_activate')


@if_docker
def test_volume_deactivate(agent, responses):
    event_test(agent, 'docker/volume_deactivate')


@if_docker
def test_instance_activate_need_pull_image(agent, responses):
    try:
        docker_client().remove_image('ibuildthecloud/helloworld:latest')
    except APIError:
        pass

    test_instance_only_activate(agent, responses)


@if_docker
def test_image_activate_no_reg_cred_pull_image(agent, responses):
    try:
        docker_client().remove_image('ibuildthecloud/helloworld:latest')
    except APIError:
        pass

    def pre(req):
        image = req['data']['imageStoragePoolMap']['image']
        image['registryCredential'] = None

    def post(req, resp):
        image_data = resp['data']['imageStoragePoolMap']['+data']
        del image_data['dockerImage']['VirtualSize']

    event_test(agent, 'docker/image_activate', pre_func=pre, post_func=post)


def _pull_image_by_name(agent, responses, image_name):
    _delete_container('/c861f990-4472-4fa1-960f-65171b544c28')
    try:
        docker_client().remove_image(image_name)
    except APIError:
        pass

    def pre(req):
        image = req['data']['imageStoragePoolMap']['image']
        remap_dockerImage(image, image_name)

    def post(req, resp):
        responseImage = resp['data']['imageStoragePoolMap']['+data']
        responseImage = responseImage['dockerImage']
        correct = False
        sent_parsed = _parse_repo_tag(image_name)
        for resp_img_uuid in responseImage['RepoTags']:
            parsed_name = _parse_repo_tag(resp_img_uuid)
            assert parsed_name['repository'] == sent_parsed['repository']
            if sent_parsed['tag'] != '':
                if sent_parsed['tag'] == 'latest':
                    if parsed_name['tag'] is not None:
                        correct = True
                else:
                    if parsed_name['tag'] == sent_parsed['tag']:
                        correct = True
            else:
                correct = True
        assert correct is True

    event_test(agent, 'docker/image_activate', pre_func=pre, post_func=post,
               no_diff=True)


def remap_dockerImage(dockerImage, image_name):
    image = dockerImage
    parsed = _parse_repo_tag(image_name)
    image['name'] = parsed['fullName']
    image['uuid'] = 'docker:' + parsed['fullName']
    image['data']['dockerImage']['fullName'] = parsed['fullName']
    image['data']['dockerImage']['server'] = parsed['server']
    image['data']['dockerImage']['repository'] = parsed['repository']
    image['data']['dockerImage']['lookUpName'] = parsed['lookUpName']
    image['data']['dockerImage']['qualifiedName'] = parsed['qualifiedName']
    image['data']['dockerImage']['namespace'] = parsed['namespace']
    image['data']['dockerImage']['tag'] = parsed['tag']


@if_docker
def test_image_pull_variants(agent, responses):
    image_names = [
        'ibuildthecloud/helloworld:latest',
        'ibuildthecloud/helloworld',
        'tianon/true',
        'tianon/true:latest',
        # 'registry.rancher.io/rancher/scratch', Need to make our registry
        # 'registry.rancher.io/rancher/scratch:latest', Support non-authed
        # 'registry.rancher.io/rancher/scratch:new_stuff',  pulls.
        'cirros',
        'cirros:latest',
        'cirros:0.3.3'
    ]

    for i in image_names:
        _pull_image_by_name(agent, responses, i)


@if_docker
def _test_image_pull_credential(agent, responses):
    _delete_container('/c861f990-4472-4fa1-960f-65171b544c28')
    image_name = 'registry.rancher.io/rancher/loop'

    try:
        docker_client().remove_image(image_name)
    except APIError:
        pass

    def pre(req):
        image = req['data']['imageStoragePoolMap']['image']
        remap_dockerImage(image, image_name)
        image['registryCredential'] = {
            'publicValue': 'rancher',
            'secretValue': 'rancher',
            'data': {
                'fields': {
                    'email': 'test@rancher.com',
                }
            },
            'registry': {
                'data': {
                    'fields': {
                        'serverAddress': 'registry.rancher.io'
                    }
                }
            }
        }

    def post(req, resp):
        responseImage = resp['data']['imageStoragePoolMap']['+data']
        responseImage = responseImage['dockerImage']
        correct = False
        sent_parsed = _parse_repo_tag(image_name)
        for resp_img_uuid in responseImage['RepoTags']:
            parsed_name = _parse_repo_tag(resp_img_uuid)
            assert parsed_name['repository'] == sent_parsed['repository']
            if sent_parsed['tag'] != '':
                if sent_parsed['tag'] == 'latest':
                    if parsed_name['tag'] is not None:
                        correct = True
                else:
                    if parsed_name['tag'] == sent_parsed['tag']:
                        correct = True
            else:
                correct = True
        assert correct is True

    event_test(agent, 'docker/image_activate', pre_func=pre, post_func=post,
               no_diff=True)


@if_docker
def _test_instance_pull_credential(agent, responses):
    _delete_container('/c861f990-4472-4fa1-960f-65171b544c28')
    image_name = 'registry.rancher.io/rancher/loop'

    try:
        docker_client().remove_image(image_name)
    except APIError:
        pass

    def pre(req):
        instance = req['data']['instanceHostMap']['instance']
        image = instance['image']
        remap_dockerImage(image, image_name)
        image['registryCredential'] = {
            'publicValue': 'rancher',
            'secretValue': 'rancher',
            'data': {
                'fields': {
                    'email': 'test@rancher.com',
                }
            },
            'registry': {
                'data': {
                    'fields': {
                        'serverAddress': 'registry.rancher.io'
                    }
                }
            }
        }

    def post(req, resp):
        responseInstance = resp['data']['instanceHostMap']['instance']['+data']
        resp_img_uuid = responseInstance['dockerContainer']['Image']
        parsed_name = _parse_repo_tag(resp_img_uuid)
        sent_parsed = _parse_repo_tag(image_name)
        assert parsed_name['repository'] == sent_parsed['repository']
        if sent_parsed['tag'] != '':
            if sent_parsed['tag'] == 'latest':
                assert parsed_name['tag'] is not None
            else:
                assert parsed_name['tag'] == sent_parsed['tag']

    event_test(agent, 'docker/instance_activate', pre_func=pre, post_func=post,
               no_diff=True)


def image_pull_invalid_credential(agent, responses):
    _delete_container('/c861f990-4472-4fa1-960f-65171b544c28')
    image_name = 'quay.io/wizardofmath/whisperdocker'

    try:
        docker_client().remove_image(image_name)
    except APIError:
        pass

    def pre(req):
        instance = req['data']['instanceHostMap']['instance']
        for nic in instance['nics']:
            nic['macAddress'] = ''
        instance['data']['fields']['imageUuid'] = image_name
        instance['registryCredential'] = {
            'publicValue': 'wizardofmath+whisper',
            'secretValue': 'W0IUYDBM2VORHM4DTTEHSMKLXGCG3KD',
            'data': {
                'fields': {
                    'email': 'wizardofmath+whisper@gmail.com',
                }
            },
            'storagePool': {
                'data': {
                    'fields': {
                        'serveraddress': 'https://quay.io/v1/'
                    }
                }
            }
            }

    def post(req, resp):
        responseInstance = resp['data']['instanceHostMap']['instance']['+data']
        resp_img_uuid = responseInstance['dockerContainer']['Image']
        parsed_name = _parse_repo_tag(resp_img_uuid)
        sent_parsed = _parse_repo_tag(image_name)
        assert parsed_name['repo'] == sent_parsed['repo']
        if sent_parsed['tag'] != '':
            if sent_parsed['tag'] == 'latest':
                assert parsed_name['tag'] is not None
            else:
                assert parsed_name['tag'] == sent_parsed['tag']
        responseInstance['dockerContainer']['Image'] =\
            'ibuildthecloud/helloworld:latest'
        responseInstance['dockerContainer']['Command'] = '/sleep.sh'

        instance_activate_common_validation(resp)

    event_test(agent, 'docker/image_activate', pre_func=pre, post_func=post)


@if_docker
def test_instance_only_activate(agent, responses):
    _delete_container('/c861f990-4472-4fa1-960f-65171b544c28')

    def pre(req):
        instance = req['data']['instanceHostMap']['instance']
        for nic in instance['nics']:
            nic['macAddress'] = ''

    def post(req, resp):
        docker_inspect = resp['data']['instanceHostMap']['instance']['+data'][
            'dockerInspect']
        envs = docker_inspect['Config']['Env']
        found_ip_env = False
        ip = req['data']['instanceHostMap']['instance']['nics'][
            0]['ipAddresses'][0]
        expected_ip_env_var = "RANCHER_IP={0}/{1}".format(ip.address,
                                                          ip.subnet.cidrSize)
        for env in envs:
            if env == expected_ip_env_var:
                found_ip_env = True
                break
        assert found_ip_env
        instance_activate_common_validation(resp)

    event_test(agent, 'docker/instance_activate', pre_func=pre, post_func=post)


@if_docker
def test_instance_activate_no_mac_address(agent, responses):
    _delete_container('/c861f990-4472-4fa1-960f-65171b544c28')

    def pre(req):
        instance = req['data']['instanceHostMap']['instance']
        for nic in instance['nics']:
            nic['macAddress'] = ''

    def post(req, resp):
        instance_data = resp['data']['instanceHostMap']['instance']['+data']
        docker_inspect = instance_data['dockerInspect']
        mac_received = docker_inspect['Config']['MacAddress']
        mac_nic_received = docker_inspect['NetworkSettings']['MacAddress']
        assert mac_received == ''
        assert mac_nic_received is not None
        instance_activate_common_validation(resp)

    event_test(agent, 'docker/instance_activate', pre_func=pre, post_func=post)


@if_docker
def test_instance_activate_mac_address(agent, responses):
    _delete_container('/c861f990-4472-4fa1-960f-65171b544c28')

    def post(req, resp):
        instance_data = resp['data']['instanceHostMap']['instance']['+data']
        docker_inspect = instance_data['dockerInspect']
        mac_received = docker_inspect['Config']['MacAddress']
        mac_nic_received = docker_inspect['NetworkSettings']['MacAddress']
        assert mac_nic_received == '02:03:04:05:06:07'
        assert mac_received == '02:03:04:05:06:07'
        instance_activate_common_validation(resp)

    event_test(agent, 'docker/instance_activate', post_func=post)


@if_docker
def test_instance_activate_native_container_happy_path(agent, responses):
    # Recieving an activate event for a running, pre-existing container should
    # result in the container continuin to run and the appropriate data sent
    # back in the response (like, ports, ip, inspect, etc)
    _delete_container('/native_container')

    client = docker_client()
    c = client.create_container('ibuildthecloud/helloworld',
                                name='native_container')
    client.start(c)
    inspect = docker_client().inspect_container(c['Id'])

    def pre(req):
        instance = req['data']['instanceHostMap']['instance']
        instance['externalId'] = c['Id']

    def post(req, resp):
        instance_data = resp['data']['instanceHostMap']['instance']['+data']
        docker_inspect = instance_data['dockerInspect']
        diff_dict(inspect, docker_inspect)
        assert docker_inspect['State']['Running']
        container_field_test_boiler_plate(resp)
        assert _state_file_exists(docker_inspect['Id'])

    event_test(agent, 'docker/instance_activate_native_container',
               pre_func=pre, post_func=post)


@if_docker
def test_instance_activate_native_container_not_running(agent, responses):
    # Receiving an activate event for a pre-existing stopped container
    # that Rancher never recorded as having started should result in the
    # container staying stopped and appropriate data sent in the response.
    _delete_container('/native_container')

    client = docker_client()
    c = client.create_container('ibuildthecloud/helloworld',
                                name='native_container')
    inspect = docker_client().inspect_container(c['Id'])

    def pre(req):
        instance = req['data']['instanceHostMap']['instance']
        instance['externalId'] = c['Id']

    def post(req, resp):
        instance_data = resp['data']['instanceHostMap']['instance']['+data']
        docker_inspect = instance_data['dockerInspect']
        diff_dict(inspect, docker_inspect)
        assert not docker_inspect['State']['Running']
        container_field_test_boiler_plate(resp)
        assert _state_file_exists(docker_inspect['Id'])

    event_test(agent, 'docker/instance_activate_native_container_not_running',
               pre_func=pre, post_func=post)


@if_docker
def test_instance_activate_native_container_removed(agent, responses):
    # Receiving an activate event for a pre-existing, but removed container
    # should result in the container continuing to not exist and a valid but
    # minimally populated response.
    _delete_container('/native_container')
    client = docker_client()
    c = client.create_container('ibuildthecloud/helloworld',
                                name='native_container')
    _delete_container('/native_container')

    def pre(req):
        instance = req['data']['instanceHostMap']['instance']
        instance['externalId'] = c['Id']

    def post(req, resp):
        instance_data = resp['data']['instanceHostMap']['instance']['+data']
        assert not instance_data['dockerInspect']
        assert not instance_data['dockerContainer']
        fields = instance_data['+fields']
        assert not fields['dockerIp']
        assert not fields['dockerPorts']
        assert fields['dockerHostIp']
        c = _get_container('/native_container')
        assert not c

    event_test(agent, 'docker/instance_activate_native_container_not_running',
               pre_func=pre, post_func=post, no_diff=True)


@if_docker
def test_instance_deactivate_native_container(agent, responses):
    test_instance_activate_native_container_happy_path(agent, responses)

    c = _get_container('/native_container')

    def pre(req):
        instance = req['data']['instanceHostMap']['instance']
        instance['externalId'] = c['Id']

    def post(req, resp):
        instance_data = resp['data']['instanceHostMap']['instance']['+data']
        docker_inspect = instance_data['dockerInspect']
        assert not docker_inspect['State']['Running']
        container_field_test_boiler_plate(resp)
        assert _state_file_exists(docker_inspect['Id'])

    event_test(agent, 'docker/instance_deactivate_native_container',
               pre_func=pre, post_func=post)

    def pre_second_start(req):
        instance = req['data']['instanceHostMap']['instance']
        instance['externalId'] = c['Id']
        instance['firstRunning'] = 1389656010338
        del req['data']['processData']['containerNoOpEvent']

    def post_second_start(req, resp):
        instance_data = resp['data']['instanceHostMap']['instance']['+data']
        docker_inspect = instance_data['dockerInspect']
        assert docker_inspect['State']['Running']
        container_field_test_boiler_plate(resp)
        assert _state_file_exists(docker_inspect['Id'])

    event_test(agent, 'docker/instance_activate_native_container',
               pre_func=pre_second_start, post_func=post_second_start)


def test_multiple_nics_pick_mac():
    instance = {
        'nics': [
            {
                'macAddress': '02:03:04:05:06:07',
                'deviceNumber': 0
            },
            {
                'macAddress': '02:03:04:05:06:09',
                'deviceNumber': 1
            }
        ]
    }
    instance = JsonObject(instance)
    config = {'test': 'Nothing'}
    setup_mac_and_ip(instance, config)
    assert config['mac_address'] == '02:03:04:05:06:07'


@if_docker
def test_instance_activate_ports(agent, responses):
    _delete_container('/c861f990-4472-4fa1-960f-65171b544c28')

    def post(req, resp):
        instance_data = resp['data']['instanceHostMap']['instance']['+data']
        del instance_data['dockerInspect']
        docker_container = instance_data['dockerContainer']
        fields = instance_data['+fields']
        del docker_container['Created']
        del docker_container['Id']
        del docker_container['Status']
        del fields['dockerIp']
        del resp['data']['instanceHostMap']['instance']['externalId']

        assert len(docker_container['Ports']) == 1
        assert docker_container['Ports'][0]['PrivatePort'] == 8080
        assert docker_container['Ports'][0]['Type'] == 'tcp'

    event_test(agent, 'docker/instance_activate_ports', post_func=post)


@if_docker
def test_instance_activate_links(agent, responses):
    _delete_container('/c861f990-4472-4fa1-960f-65171b544c28')

    def post(req, resp):
        id = resp['data']['instanceHostMap']['instance']
        id = id['+data']['dockerContainer']['Id']
        inspect = docker_client().inspect_container(id)
        instance_activate_common_validation(resp)

        env = inspect['Config']['Env']

        assert 'MYSQL_NAME=/cattle/mysql' in env
        assert 'MYSQL_PORT=udp://127.0.0.2:12346' in env
        assert 'MYSQL_PORT_3307_UDP=udp://127.0.0.2:12346' in env
        assert 'MYSQL_PORT_3307_UDP_ADDR=127.0.0.2' in env
        assert 'MYSQL_PORT_3307_UDP_PORT=12346' in env
        assert 'MYSQL_PORT_3307_UDP_PROTO=udp' in env

        assert 'MYSQL_PORT_3306_TCP=tcp://127.0.0.1:12345' in env
        assert 'MYSQL_PORT_3306_TCP_ADDR=127.0.0.1' in env
        assert 'MYSQL_PORT_3306_TCP_PORT=12345' in env
        assert 'MYSQL_PORT_3306_TCP_PROTO=tcp' in env

        assert 'REDIS_NAME=/cattle/redis' in env
        assert 'REDIS_PORT=udp://127.0.0.1:23456' in env
        assert 'REDIS_PORT_26_UDP=udp://127.0.0.1:23456' in env
        assert 'REDIS_PORT_26_UDP_ADDR=127.0.0.1' in env
        assert 'REDIS_PORT_26_UDP_PORT=23456' in env
        assert 'REDIS_PORT_26_UDP_PROTO=udp' in env

    event_test(agent, 'docker/instance_activate_links', post_func=post)


@if_docker
def test_instance_activate_links_no_service(agent, responses):
    _delete_container('/c861f990-4472-4fa1-960f-65171b544c28')
    _delete_container('/target_redis')
    _delete_container('/target_mysql')

    client = docker_client()
    c = client.create_container('ibuildthecloud/helloworld',
                                ports=['3307/udp', '3306/tcp'],
                                name='target_mysql')
    client.start(c, port_bindings={
        '3307/udp': ('127.0.0.2', 12346),
        '3306/tcp': ('127.0.0.2', 12345)
    })

    c = client.create_container('ibuildthecloud/helloworld',
                                name='target_redis')
    client.start(c)

    def post(req, resp):
        id = resp['data']['instanceHostMap']['instance']
        id = id['+data']['dockerContainer']['Id']
        inspect = docker_client().inspect_container(id)
        instance_activate_common_validation(resp)

        assert set(
            ['/target_mysql:/c861f990-4472-4fa1-960f-65171b544c28/mysql',
             '/target_redis:/c861f990-4472-4fa1-960f-65171b544c28/'
             'redis']) == set(inspect['HostConfig']['Links'])

    event_test(agent, 'docker/instance_activate_links_no_service',
               post_func=post)


@if_docker
def test_instance_activate_cpu_set(agent, responses):

    def pre(req):
        _delete_container('/c861f990-4472-4fa1-960f-65171b544c28')
        instance = req['data']['instanceHostMap']['instance']
        instance['data']['fields']['cpuSet'] = '0,1'

    def preNull(req):
        _delete_container('/c861f990-4472-4fa1-960f-65171b544c28')
        instance = req['data']['instanceHostMap']['instance']
        instance['data']['fields']['cpuSet'] = None

    def preEmpty(req):
        _delete_container('/c861f990-4472-4fa1-960f-65171b544c28')
        instance = req['data']['instanceHostMap']['instance']
        instance['data']['fields']['cpuSet'] = ''

    def post(req, resp):
        instance_data = resp['data']['instanceHostMap']['instance']['+data']
        docker_inspect = instance_data['dockerInspect']
        assert docker_inspect['Config']['Cpuset'] == '0,1'
        container_field_test_boiler_plate(resp)

    def postNull(req, resp):
        instance_data = resp['data']['instanceHostMap']['instance']['+data']
        docker_inspect = instance_data['dockerInspect']
        assert docker_inspect['Config']['Cpuset'] == ''
        container_field_test_boiler_plate(resp)

    def postEmpty(req, resp):
        instance_data = resp['data']['instanceHostMap']['instance']['+data']
        docker_inspect = instance_data['dockerInspect']
        assert docker_inspect['Config']['Cpuset'] == ''
        container_field_test_boiler_plate(resp)

    schema = 'docker/instance_activate_fields'
    event_test(agent, schema, pre_func=pre, post_func=post)
    event_test(agent, schema, pre_func=preNull, post_func=postNull)
    event_test(agent, schema, pre_func=preEmpty, post_func=postEmpty)


@if_docker
def test_instance_activate_memory_swap(agent, responses):
    _delete_container('/c861f990-4472-4fa1-960f-65171b544c28')

    def pre(req):
        instance = req['data']['instanceHostMap']['instance']
        instance['data']['fields']['memory'] = 8000000
        instance['data']['fields']['memorySwap'] = 16000000

    def post(req, resp):
        instance_data = resp['data']['instanceHostMap']['instance']['+data']
        docker_inspect = instance_data['dockerInspect']
        assert docker_inspect['Config']['MemorySwap'] == 16000000
        assert docker_inspect['Config']['Memory'] == 8000000
        container_field_test_boiler_plate(resp)

    schema = 'docker/instance_activate_fields'
    event_test(agent, schema, pre_func=pre, post_func=post)


@if_docker
def test_instance_activate_entrypoint(agent, responses):
    _delete_container('/c861f990-4472-4fa1-960f-65171b544c28')

    def pre(req):
        instance = req['data']['instanceHostMap']['instance']
        instance['data']['fields']['entryPoint'] = ["./sleep.sh"]

    def post(req, resp):
        instance_data = resp['data']['instanceHostMap']['instance']['+data']
        docker_inspect = instance_data['dockerInspect']
        assert docker_inspect['Config']['Entrypoint'] == ["./sleep.sh"]
        docker_container = instance_data['dockerContainer']
        docker_container['Command'] = "/sleep.sh"
        container_field_test_boiler_plate(resp)

    schema = 'docker/instance_activate_fields'
    event_test(agent, schema, pre_func=pre, post_func=post)


@if_docker
def test_instance_activate_memory(agent, responses):
    _delete_container('/c861f990-4472-4fa1-960f-65171b544c28')

    def pre(req):
        instance = req['data']['instanceHostMap']['instance']
        instance['data']['fields']['memory'] = 8000000

    def post(req, resp):
        instance_data = resp['data']['instanceHostMap']['instance']['+data']
        docker_inspect = instance_data['dockerInspect']
        assert docker_inspect['Config']['Memory'] == 8000000
        container_field_test_boiler_plate(resp)

    schema = 'docker/instance_activate_fields'
    event_test(agent, schema, pre_func=pre, post_func=post)


@if_docker
def test_instance_activate_tty(agent, responses):

    def preFalse(req):
        _delete_container('/c861f990-4472-4fa1-960f-65171b544c28')
        instance = req['data']['instanceHostMap']['instance']
        instance['data']['fields']['tty'] = False

    def pre(req):
        _delete_container('/c861f990-4472-4fa1-960f-65171b544c28')
        instance = req['data']['instanceHostMap']['instance']
        instance['data']['fields']['tty'] = True

    def postFalse(req, resp):
        instance_data = resp['data']['instanceHostMap']['instance']['+data']
        docker_inspect = instance_data['dockerInspect']
        assert not docker_inspect['Config']['Tty']
        container_field_test_boiler_plate(resp)

    def post(req, resp):
        instance_data = resp['data']['instanceHostMap']['instance']['+data']
        docker_inspect = instance_data['dockerInspect']
        assert docker_inspect['Config']['Tty']
        container_field_test_boiler_plate(resp)

    schema = 'docker/instance_activate_fields'
    event_test(agent, schema, pre_func=pre, post_func=post)
    event_test(agent, schema, pre_func=preFalse, post_func=postFalse)


@if_docker
def test_instance_activate_stdinOpen(agent, responses):

    def preTrueDetach(req):
        _delete_container('/c861f990-4472-4fa1-960f-65171b544c28')
        instance = req['data']['instanceHostMap']['instance']
        instance['data']['fields']['stdinOpen'] = True
        instance['data']['fields']['detach'] = True

    def preFalse(req):
        _delete_container('/c861f990-4472-4fa1-960f-65171b544c28')
        instance = req['data']['instanceHostMap']['instance']
        instance['data']['fields']['stdinOpen'] = False
        instance['data']['fields']['detach'] = False

    def pre(req):
        _delete_container('/c861f990-4472-4fa1-960f-65171b544c28')
        instance = req['data']['instanceHostMap']['instance']
        instance['data']['fields']['stdinOpen'] = True
        instance['data']['fields']['detach'] = False

    def postTrueDetach(req, resp):
        instance_data = resp['data']['instanceHostMap']['instance']['+data']
        docker_inspect = instance_data['dockerInspect']
        assert not docker_inspect['Config']['StdinOnce']
        assert docker_inspect['Config']['OpenStdin']
        assert not docker_inspect['Config']['AttachStdin']
        container_field_test_boiler_plate(resp)

    def postFalse(req, resp):
        instance_data = resp['data']['instanceHostMap']['instance']['+data']
        docker_inspect = instance_data['dockerInspect']
        assert not docker_inspect['Config']['StdinOnce']
        assert not docker_inspect['Config']['OpenStdin']
        assert not docker_inspect['Config']['AttachStdin']
        container_field_test_boiler_plate(resp)

    def post(req, resp):
        instance_data = resp['data']['instanceHostMap']['instance']['+data']
        docker_inspect = instance_data['dockerInspect']
        assert docker_inspect['Config']['StdinOnce']
        assert docker_inspect['Config']['OpenStdin']
        assert docker_inspect['Config']['AttachStdin']
        container_field_test_boiler_plate(resp)

    schema = 'docker/instance_activate_fields'
    event_test(agent, schema, pre_func=pre, post_func=post)
    event_test(agent, schema, pre_func=preFalse, post_func=postFalse)
    event_test(agent, schema, pre_func=preTrueDetach, post_func=postTrueDetach)


@if_docker
def test_instance_activate_lxc_conf(agent, responses):
    _delete_container('/c861f990-4472-4fa1-960f-65171b544c28')
    expectedLxcConf = {"lxc.network.type": "veth"}

    def pre(req):
        instance = req['data']['instanceHostMap']['instance']
        instance['data']['fields']['lxcConf'] = expectedLxcConf

    def post(req, resp):
        instance_data = resp['data']['instanceHostMap']['instance']['+data']
        docker_inspect = instance_data['dockerInspect']
        for conf in docker_inspect['HostConfig']['LxcConf']:
            assert expectedLxcConf[conf['Key']] == conf['Value']
        container_field_test_boiler_plate(resp)

    schema = 'docker/instance_activate_fields'
    event_test(agent, schema, pre_func=pre, post_func=post)


@if_docker
def test_instance_activate_domainname(agent, responses):
    _delete_container('/c861f990-4472-4fa1-960f-65171b544c28')

    def pre(req):
        instance = req['data']['instanceHostMap']['instance']
        instance['data']['fields']['domainName'] = "rancher.io"

    def post(req, resp):
        instance_data = resp['data']['instanceHostMap']['instance']['+data']
        docker_inspect = instance_data['dockerInspect']
        assert docker_inspect['Config']['Domainname'] == "rancher.io"
        container_field_test_boiler_plate(resp)

    schema = 'docker/instance_activate_fields'
    event_test(agent, schema, pre_func=pre, post_func=post)


@if_docker
def test_instance_activate_devices(agent, responses):
    _delete_container('/c861f990-4472-4fa1-960f-65171b544c28')
    input_devices = ['/dev/null:/dev/xnull', '/dev/random:/dev/xrandom:rw']
    expected_devices = {}
    for input_device in input_devices:
        parts_of_device = input_device.split(':')
        key = parts_of_device[0]
        expected_devices[key] = {
            "PathOnHost": parts_of_device[0],
            "PathInContainer": parts_of_device[1]
        }
        if len(parts_of_device) == 3:
            expected_devices[key]["CgroupPermissions"] = parts_of_device[2]
        else:
            expected_devices[key]["CgroupPermissions"] = "rwm"

    def pre(req):
        instance = req['data']['instanceHostMap']['instance']
        instance['data']['fields']['devices'] = input_devices

    def post(req, resp):
        instance_data = resp['data']['instanceHostMap']['instance']['+data']
        docker_inspect = instance_data['dockerInspect']
        actual_devices = docker_inspect['HostConfig']['Devices']

        assert len(expected_devices) == len(actual_devices)

        for act_dvc in actual_devices:
            exp_dvc = expected_devices[act_dvc['PathOnHost']]
            assert exp_dvc['PathOnHost'] == act_dvc['PathOnHost']
            assert exp_dvc['PathInContainer'] == act_dvc['PathInContainer']
            assert exp_dvc['CgroupPermissions'] == act_dvc['CgroupPermissions']

        container_field_test_boiler_plate(resp)

    schema = 'docker/instance_activate_fields'
    event_test(agent, schema, pre_func=pre, post_func=post)


@if_docker
def test_instance_activate_dns(agent, responses):
    _delete_container('/c861f990-4472-4fa1-960f-65171b544c28')

    def pre(req):
        instance = req['data']['instanceHostMap']['instance']
        instance['data']['fields']['dns'] = ["1.2.3.4", "8.8.8.8"]
        instance['data']['fields']['dnsSearch'] = ["5.6.7.8", "7.7.7.7"]

    def post(req, resp):
        instance_data = resp['data']['instanceHostMap']['instance']['+data']
        docker_inspect = instance_data['dockerInspect']
        actual_dns = docker_inspect['HostConfig']['Dns']
        actual_dns_search = docker_inspect['HostConfig']['DnsSearch']
        assert set(actual_dns) == set(["8.8.8.8", "1.2.3.4"])
        assert set(actual_dns_search) == set(["7.7.7.7", "5.6.7.8"])
        container_field_test_boiler_plate(resp)

    schema = 'docker/instance_activate_fields'
    event_test(agent, schema, pre_func=pre, post_func=post)


@if_docker
def test_instance_activate_caps(agent, responses):
    _delete_container('/c861f990-4472-4fa1-960f-65171b544c28')

    def pre(req):
        instance = req['data']['instanceHostMap']['instance']
        instance['data']['fields']['capAdd'] = ["MKNOD", "SYS_ADMIN"]
        instance['data']['fields']['capDrop'] = ["MKNOD", "SYS_ADMIN"]

    def post(req, resp):
        instance_data = resp['data']['instanceHostMap']['instance']['+data']
        docker_inspect = instance_data['dockerInspect']
        set_actual_cap_add = set(docker_inspect['HostConfig']['CapAdd'])
        set_expected_cap_add = set(["MKNOD", "SYS_ADMIN"])
        assert set_actual_cap_add == set_expected_cap_add
        set_actual_cap_drop = set(docker_inspect['HostConfig']['CapDrop'])
        set_expected_cap_drop = set(["MKNOD", "SYS_ADMIN"])
        assert set_actual_cap_drop == set_expected_cap_drop
        container_field_test_boiler_plate(resp)

    schema = 'docker/instance_activate_fields'
    event_test(agent, schema, pre_func=pre, post_func=post)


@if_docker
def test_instance_activate_privileged(agent, responses):

    def preTrue(req):
        _delete_container('/c861f990-4472-4fa1-960f-65171b544c28')
        instance = req['data']['instanceHostMap']['instance']
        instance['data']['fields']['privileged'] = True

    def preFalse(req):
        instance = req['data']['instanceHostMap']['instance']
        instance['data']['fields']['privileged'] = False

    def postTrue(req, resp):
        instance_data = resp['data']['instanceHostMap']['instance']['+data']
        _delete_container('/c861f990-4472-4fa1-960f-65171b544c28')
        docker_inspect = instance_data['dockerInspect']
        assert docker_inspect['HostConfig']['Privileged']
        container_field_test_boiler_plate(resp)

    def postFalse(req, resp):
        instance_data = resp['data']['instanceHostMap']['instance']['+data']
        docker_inspect = instance_data['dockerInspect']
        assert not docker_inspect['HostConfig']['Privileged']
        container_field_test_boiler_plate(resp)

    schema = 'docker/instance_activate_fields'
    event_test(agent, schema, pre_func=preTrue, post_func=postTrue)
    event_test(agent, schema, pre_func=preFalse, post_func=postFalse)


@if_docker
def test_instance_restart_policy(agent, responses):
    _delete_container('/c861f990-4472-4fa1-960f-65171b544c28')
    expected_restart_pol_1 = {"maximumRetryCount": 0,
                              "name": "always"}
    expected_restart_pol_2 = {"name": "on-failure",
                              "maximumRetryCount": 2,
                              }
    expected_restart_pol_3 = {"name": "always"}

    def pre(req):
        instance = req['data']['instanceHostMap']['instance']
        instance['data']['fields']['restartPolicy'] = expected_restart_pol_1

    def pre_failure_policy(req):
        _delete_container('/c861f990-4472-4fa1-960f-65171b544c28')
        instance = req['data']['instanceHostMap']['instance']
        instance['data']['fields']['restartPolicy'] = expected_restart_pol_2

    def pre_name_policy(req):
        _delete_container('/c861f990-4472-4fa1-960f-65171b544c28')
        instance = req['data']['instanceHostMap']['instance']
        instance['data']['fields']['restartPolicy'] = expected_restart_pol_3

    def post(req, resp):
        instance_data = resp['data']['instanceHostMap']['instance']['+data']
        docker_inspect = instance_data['dockerInspect']
        act_restart_pol = docker_inspect['HostConfig']['RestartPolicy']
        assert act_restart_pol['Name'] == expected_restart_pol_1['name']
        assert act_restart_pol['MaximumRetryCount'] == expected_restart_pol_1[
            'maximumRetryCount']
        container_field_test_boiler_plate(resp)

    def post_failure_policy(req, resp):
        instance_data = resp['data']['instanceHostMap']['instance']['+data']
        docker_inspect = instance_data['dockerInspect']
        act_restart_pol = docker_inspect['HostConfig']['RestartPolicy']
        assert act_restart_pol['Name'] == expected_restart_pol_2['name']
        assert act_restart_pol['MaximumRetryCount'] == expected_restart_pol_2[
            'maximumRetryCount']
        container_field_test_boiler_plate(resp)

    def post_name_policy(req, resp):
        instance_data = resp['data']['instanceHostMap']['instance']['+data']
        docker_inspect = instance_data['dockerInspect']
        act_restart_pol = docker_inspect['HostConfig']['RestartPolicy']
        assert act_restart_pol['Name'] == expected_restart_pol_3['name']
        container_field_test_boiler_plate(resp)

    schema = 'docker/instance_activate_fields'
    event_test(agent, schema, pre_func=pre, post_func=post)
    event_test(agent, schema, pre_func=pre_failure_policy,
               post_func=post_failure_policy)
    event_test(agent, schema, pre_func=pre_name_policy,
               post_func=post_name_policy)


@if_docker
def test_instance_activate_cpu_shares(agent, responses):
    _delete_container('/c861f990-4472-4fa1-960f-65171b544c28')

    def pre(req):
        instance = req['data']['instanceHostMap']['instance']
        instance['data']['fields']['cpuShares'] = 400

    def post(req, resp):
        instance_data = resp['data']['instanceHostMap']['instance']['+data']
        docker_inspect = instance_data['dockerInspect']
        assert docker_inspect['Config']['CpuShares'] == 400
        container_field_test_boiler_plate(resp)

    schema = 'docker/instance_activate_fields'
    event_test(agent, schema, pre_func=pre, post_func=post)


@if_docker
def test_instance_activate_ipsec(agent, responses):
    _delete_container('/c861f990-4472-4fa1-960f-65171b544c28')

    def post(req, resp):
        instance_activate_common_validation(resp)

    event_test(agent, 'docker/instance_activate_ipsec', post_func=post)


@if_docker
def test_instance_activate_agent_instance_localhost(agent, responses):
    CONFIG_OVERRIDE['CONFIG_URL'] = 'https://localhost:1234/a/path'
    _delete_container('/c861f990-4472-4fa1-960f-65171b544c28')

    def post(req, resp):
        id = resp['data']['instanceHostMap']['instance']
        id = id['+data']['dockerContainer']['Id']
        inspect = docker_client().inspect_container(id)
        instance_activate_common_validation(resp)

        port = Config.api_proxy_listen_port()
        assert 'CATTLE_CONFIG_URL_SCHEME=https' in inspect['Config']['Env']
        assert 'CATTLE_CONFIG_URL_PATH=/a/path' in inspect['Config']['Env']
        assert 'CATTLE_CONFIG_URL_PORT={0}'.format(port) in \
            inspect['Config']['Env']

    event_test(agent, 'docker/instance_activate_agent_instance',
               post_func=post)


@if_docker
def test_instance_activate_agent_instance(agent, responses):
    CONFIG_OVERRIDE['CONFIG_URL'] = 'https://something.fake:1234/a/path'
    _delete_container('/c861f990-4472-4fa1-960f-65171b544c28')

    def post(req, resp):
        id = resp['data']['instanceHostMap']['instance']
        id = id['+data']['dockerContainer']['Id']

        inspect = docker_client().inspect_container(id)
        instance_activate_common_validation(resp)

        port = Config.api_proxy_listen_port()
        assert 'CATTLE_CONFIG_URL={0}'.format(Config.config_url()) in \
               inspect['Config']['Env']
        assert 'CATTLE_CONFIG_URL_SCHEME=https' not in inspect['Config']['Env']
        assert 'CATTLE_CONFIG_URL_PATH=/a/path' not in inspect['Config']['Env']
        assert 'CATTLE_CONFIG_URL_PORT={0}'.format(port) not in \
               inspect['Config']['Env']
        assert 'ENV1=value1' in inspect['Config']['Env']

    event_test(agent, 'docker/instance_activate_agent_instance',
               post_func=post)


def _sort_ports(docker_container):
    docker_container['Ports'] = sorted(docker_container['Ports'],
                                       key=lambda x: 1-x['PrivatePort'])
    return docker_container


@if_docker
def test_instance_activate_volumes(agent, responses):
    _delete_container('/c-c861f990-4472-4fa1-960f-65171b544c28')
    _delete_container('/target_volumes_from_by_uuid')
    _delete_container('/target_volumes_from_by_id')

    client = docker_client()
    c = client.create_container('ibuildthecloud/helloworld',
                                volumes=['/volumes_from_path_by_uuid'],
                                name='target_volumes_from_by_uuid')
    client.start(c)

    c2 = client.create_container('ibuildthecloud/helloworld',
                                 volumes=['/volumes_from_path_by_id'],
                                 name='target_volumes_from_by_id')
    client.start(c2)

    def pre(req):
        instance = req['data']['instanceHostMap']['instance']
        instance['dataVolumesFromContainers'][1]['externalId'] = c2['Id']

    def post(req, resp):
        instance_data = resp['data']['instanceHostMap']['instance']['+data']
        inspect = instance_data['dockerInspect']

        assert inspect['Volumes']['/host/proc'] == '/proc'
        assert inspect['Volumes']['/host/sys'] == '/sys'
        assert inspect['Volumes']['/random'] is not None
        assert inspect['Volumes']['/volumes_from_path_by_uuid'] is not None
        assert inspect['Volumes']['/volumes_from_path_by_id'] is not None

        assert len(inspect['Volumes']) == 5

        assert inspect['VolumesRW'] == {
            '/host/proc': True,
            '/host/sys': False,
            '/random': True,
            '/volumes_from_path_by_uuid': True,
            '/volumes_from_path_by_id': True,

        }

        assert set(['/sys:/host/sys:ro', '/proc:/host/proc:rw']) == set(
            inspect['HostConfig']['Binds'])

        instance_activate_common_validation(resp)

    event_test(agent, 'docker/instance_activate_volumes', pre_func=pre,
               post_func=post)


@if_docker
def test_instance_activate_null_command(agent, responses):
    _delete_container('/c-c861f990-4472-4fa1-960f-65171b544c28')

    def post(req, resp):
        instance_activate_common_validation(resp)

    event_test(agent, 'docker/instance_activate_command_null', post_func=post)


@if_docker
def test_instance_activate_command(agent, responses):
    _delete_container('/c-c861f990-4472-4fa1-960f-65171b544c28')

    def post(req, resp):
        instance_activate_common_validation(resp)

    event_test(agent, 'docker/instance_activate_command', post_func=post)


@if_docker
def test_instance_activate_command_args(agent, responses):
    _delete_container('/ca-c861f990-4472-4fa1-960f-65171b544c28')

    def post(req, resp):
        instance_activate_common_validation(resp)

    event_test(agent, 'docker/instance_activate_command_args', post_func=post)


@if_docker
def test_instance_deactivate(agent, responses):
    test_instance_only_activate(agent, responses)

    def post(req, resp):
        container_field_test_boiler_plate(resp)

    start = time.time()
    event_test(agent, 'docker/instance_deactivate', post_func=post)
    end = time.time()

    assert end - start < 1.2

    def pre(req):
        req['data']['processData']['timeout'] = 1

    test_instance_only_activate(agent, responses)
    start = time.time()
    event_test(agent, 'docker/instance_deactivate', pre_func=pre,
               post_func=post)
    end = time.time()

    assert end - start > 1


def ping_post_process(req, resp):
        hostname = Config.hostname()
        pool_name = hostname + ' Storage Pool'
        resources = resp['data']['resources']

        uuid = 'c861f990-4472-4fa1-960f-65171b544c28'
        instances = filter(lambda x: x['type'] == 'instance' and
                           x['uuid'] == uuid, resources)
        assert len(instances) == 1
        instance = instances[0]
        assert instance['dockerId'] is not None
        del instance['dockerId']

        resources = filter(lambda x: x.get('kind') == 'docker', resources)
        resources.append(instance)

        resp['data']['resources'] = resources

        assert resp['data']['resources'][0]['name'] == hostname
        assert resp['data']['resources'][1]['name'] == pool_name
        resp['data']['resources'][0]['name'] = 'localhost'
        resp['data']['resources'][1]['name'] = 'localhost Storage Pool'


@if_docker
def test_ping(agent, responses, mocker):
    mocker.patch.object(HostInfo, 'collect_data',
                        return_value=json_data('docker/host_info_resp'))

    test_instance_only_activate(agent, responses)

    CONFIG_OVERRIDE['DOCKER_UUID'] = 'testuuid'
    CONFIG_OVERRIDE['PHYSICAL_HOST_UUID'] = 'hostuuid'

    event_test(agent, 'docker/ping', post_func=ping_post_process)


@if_docker
def test_ping_stat_exception(agent, responses, mocker):
    mocker.patch.object(HostInfo, 'collect_data',
                        side_effect=ValueError('Bad Value Found'))

    test_instance_only_activate(agent, responses)

    CONFIG_OVERRIDE['DOCKER_UUID'] = 'testuuid'
    CONFIG_OVERRIDE['PHYSICAL_HOST_UUID'] = 'hostuuid'

    event_test(agent, 'docker/ping_stat_exception',
               post_func=ping_post_process)


@if_docker
def test_volume_purge(agent, responses):
    _delete_container('/c-c861f990-4472-4fa1-960f-65171b544c28')
    _delete_container('/target_volumes_from')

    client = docker_client()
    c = client.create_container('ibuildthecloud/helloworld',
                                volumes=['/volumes_from_path'],
                                name='target_volumes_from')
    client.start(c)
    # TODO Figure out a better way to test this. Because purging a volume
    # means removing it from disk, we run into trouble testing when
    # boot2docker is in the picture because the locally running agent cannot
    # see inside the b2d vm. We do currently test this functionality fully
    # in the integration test suite.
    event_test(agent, 'docker/volume_purge')


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
    assert _state_file_exists(docker_id)


@if_docker
def test_instance_activate_ipsec_network_agent(agent, responses):
    _delete_container('/c861f990-4472-4fa1-960f-65171b544c28')

    def post(req, resp):
        instance_activate_common_validation(resp)

    event_test(agent, 'docker/instance_activate_ipsec_network_agent',
               post_func=post)


@if_docker
def test_instance_activate_ipsec_lb_agent(agent, responses):
    _delete_container('/c861f990-4472-4fa1-960f-65171b544c28')

    def post(req, resp):
        instance_activate_common_validation(resp)

    event_test(agent, 'docker/instance_activate_ipsec_lb_agent',
               post_func=post)


def _parse_repo_tag(image):
        namespace = None
        repo = None
        tag = None
        server = 'index.docker.io'
        if image is None:
            return None
        forwardSlash = image.split("/")
        if len(forwardSlash) <= 3:
            if len(forwardSlash) == 1:
                split2 = forwardSlash[0].split(":")
                if len(split2) == 1:
                    tag = "latest"
                    repo = image
                elif len(split2) == 2:
                    tag = split2[1]
                    repo = split2[0]
            elif len(forwardSlash) == 2:
                first = forwardSlash[0]
                second = forwardSlash[1].split(":")
                if '.' in first or ':' in first or\
                        'localhost' in first:
                    server = first
                else:
                    namespace = first
                if len(second) == 2:
                    repo = second[0]
                    tag = second[1]
                else:
                    repo = forwardSlash[1]
                    tag = 'latest'
            elif len(forwardSlash) == 3:
                server = forwardSlash[0]
                namespace = forwardSlash[1]
                split2 = forwardSlash[2].split(':')
                if len(split2) == 1:
                    repo = forwardSlash[2]
                    tag = 'latest'
                else:
                    repo = split2[0]
                    tag = split2[1]
            else:
                return None
        if namespace is not None:
            lookUpName = namespace + '/' + repo
        else:
            lookUpName = repo

        if server == "index.docker.io":
            if namespace is None:
                qualifiedName = repo
            else:
                qualifiedName = namespace + "/" + repo

        else:
            if namespace is None:
                qualifiedName = server + "/" + repo
            else:
                qualifiedName = server + "/" + namespace + "/" + repo

        return dict(repository=repo,
                    lookUpName=lookUpName,
                    server=server,
                    namespace=namespace,
                    tag=tag,
                    fullName=image,
                    qualifiedName=qualifiedName)


def _cleanup_volmgr():
    test_root = "/tmp/volmgr_test"
    CONFIG_OVERRIDE["VOLMGR_ENABLED"] = "True"
    CONFIG_OVERRIDE["VOLMGR_LOG_FILE"] = os.path.join(test_root, "volmgr.log")
    CONFIG_OVERRIDE["VOLMGR_ROOT"] = os.path.join(test_root, "volmgr")
    CONFIG_OVERRIDE["VOLMGR_MOUNT_DIR"] = os.path.join(test_root,
                                                       "volmgr_mounts")
    CONFIG_OVERRIDE["VOLMGR_DM_DATA_FILE"] = \
        os.path.join(test_root, "volmgr_data_file")
    CONFIG_OVERRIDE["VOLMGR_DM_METADATA_FILE"] = \
        os.path.join(test_root, "volmgr_metadata_file")
    CONFIG_OVERRIDE["VOLMGR_BLOCKSTORE_DIR"] = \
        os.path.join(test_root, "volmgr_blockstore")
    CONFIG_OVERRIDE["VOLMGR_MOUNT_NAMESPACE_FD"] = "/proc/1/ns/mnt"
    if os.path.exists(test_root):
        shutil.rmtree(test_root)


@if_docker
def _volmgr_setup(mocker):
    mocker.patch.object(service, "create_pool_files")
    mocker.patch.object(service, "register_loopback", size_effect=[
        "/dev/testloop0", "/dev/testloop1"
    ])
    mocker.patch.object(service, "cleanup_loopback")
    mocker.patch.object(service, "mounted")

    mocker.patch.object(service.VolmgrService, "init")
    blockstore_uuid = "57c26b32-b3f3-4ceb-8a26-3c567d7d4166"
    mocker.patch.object(service.VolmgrService, "register_vfs_blockstore",
                        return_value=blockstore_uuid)
    _cleanup_volmgr()
    v = Volmgr()
    v.on_startup()
    assert os.path.exists(CONFIG_OVERRIDE["VOLMGR_ROOT"])
    assert os.path.exists(CONFIG_OVERRIDE["VOLMGR_MOUNT_DIR"])
    assert os.path.exists(CONFIG_OVERRIDE["VOLMGR_BLOCKSTORE_DIR"])


@if_docker
def test_volmgr_instance_activate_volumes(agent, responses, mocker):
    _volmgr_setup(mocker)
    _delete_container('/c-c861f990-4472-4fa1-960f-65171b544c28')

    volmgr_mount = CONFIG_OVERRIDE["VOLMGR_MOUNT_DIR"]
    volume_uuid = "0bcc6a7f-0c46-4d06-af51-224a47deeea8"

    create_volume = mocker.patch.object(service.VolmgrService, "create_volume",
                                        return_value=volume_uuid)
    add_volume = mocker.patch.object(service.VolmgrService,
                                     "add_volume_to_blockstore")
    mount_volume = mocker.patch.object(service.VolmgrService, "mount_volume")

    def post(req, resp):
        create_volume.assert_called()
        add_volume.assert_called()
        mount_volume.assert_called()

        instance_data = resp['data']['instanceHostMap']['instance']['+data']
        inspect = instance_data['dockerInspect']

        assert len(inspect['Volumes']) == 1
        mpath = inspect['Volumes']['/opt']

        assert mpath is not None

        # Cannot use startswith because boot2docker link /tmp to /mnt/sda1/tmp
        # which result in docker volume mount shows in different path.
        assert path.join(volmgr_mount, "default/test",
                         volume_uuid) in mpath

        assert inspect['VolumesRW'] == {
            '/opt': True,
            }

        instance_activate_common_validation(resp)

    event_test(agent, 'docker/volmgr_instance_activate_volumes',
               post_func=post)


@if_docker
def test_volmgr_snapshot_create(agent, responses, mocker):
    _cleanup_volmgr()
    snapshot_uuid = "8464e7bf-0b07-417c-b6cf-a253a47dc6bb"
    create_snapshot = mocker.patch.object(service.VolmgrService,
                                          "create_snapshot",
                                          return_value=snapshot_uuid)
    volume_uuid = "0bcc6a7f-0c46-4d06-af51-224a47deeea8"

    def post_create(req, resp):
        create_snapshot.assert_called_once_with(volume_uuid)
        snapshot = resp["data"]["snapshot"]
        assert snapshot["+data"]["+fields"]["managedSnapshotUUID"] == \
            snapshot_uuid
        assert snapshot["+data"]["+fields"]["managedVolumeUUID"] == \
            volume_uuid
        del resp["data"]["snapshot"]["+data"]

    event_test(agent, 'docker/volmgr_snapshot_create', post_func=post_create)


@if_docker
def test_volmgr_snapshot_backup(agent, responses, mocker):
    _cleanup_volmgr()
    snapshot_uuid = "8464e7bf-0b07-417c-b6cf-a253a47dc6bb"
    volume_uuid = "0bcc6a7f-0c46-4d06-af51-224a47deeea8"
    backup_snapshot = mocker.patch.object(service.VolmgrService,
                                          "backup_snapshot_to_blockstore")
    blockstore_uuid = "57c26b32-b3f3-4ceb-8a26-3c567d7d4166"

    def pre(req):
        snapshot = req["data"]["snapshotStoragePoolMap"]["snapshot"]
        snapshot["data"]["fields"]["managedSnapshotUUID"] = snapshot_uuid
        snapshot["data"]["fields"]["managedVolumeUUID"] = volume_uuid
        sp = req["data"]["snapshotStoragePoolMap"]["storagePool"]
        sp["data"]["fields"]["blockstoreUUID"] = blockstore_uuid

    def post(req, resp):
        backup_snapshot.assert_called_once_with(snapshot_uuid,
                                                volume_uuid,
                                                blockstore_uuid)

    event_test(agent, 'docker/volmgr_snapshot_backup',
               pre_func=pre, post_func=post)


@if_docker
def test_volmgr_snapshot_remove(agent, responses, mocker):
    _cleanup_volmgr()
    snapshot_uuid = "8464e7bf-0b07-417c-b6cf-a253a47dc6bb"
    volume_uuid = "0bcc6a7f-0c46-4d06-af51-224a47deeea8"
    blockstore_uuid = "57c26b32-b3f3-4ceb-8a26-3c567d7d4166"

    delete_snapshot = mocker.patch.object(service.VolmgrService,
                                          "delete_snapshot")
    remove_snapshot_from_blockstore = mocker.patch.object(
        service.VolmgrService, "remove_snapshot_from_blockstore")

    def pre(req):
        snapshot = req["data"]["snapshotStoragePoolMap"]["snapshot"]
        snapshot["data"]["fields"]["managedSnapshotUUID"] = snapshot_uuid
        snapshot["data"]["fields"]["managedVolumeUUID"] = volume_uuid
        sp = req["data"]["snapshotStoragePoolMap"]["storagePool"]
        sp["data"]["fields"]["blockstoreUUID"] = blockstore_uuid

    def post(req, resp):
        delete_snapshot.assert_called_once_with(snapshot_uuid, volume_uuid)
        remove_snapshot_from_blockstore.assert_called_with(
            snapshot_uuid,
            volume_uuid,
            blockstore_uuid)

    event_test(agent, 'docker/volmgr_snapshot_remove',
               pre_func=pre, post_func=post)


@if_docker
def test_volmgr_restore_snapshot(agent, responses, mocker):
    # need to setup path for previous volume
    test_volmgr_instance_activate_volumes(agent, responses, mocker)

    _delete_container("c-5f7d6bf1-0528-439d-abca-49daf59002aa")

    volmgr_mount = CONFIG_OVERRIDE["VOLMGR_MOUNT_DIR"]
    old_volume_uuid = "0bcc6a7f-0c46-4d06-af51-224a47deeea8"
    snapshot_uuid = "8464e7bf-0b07-417c-b6cf-a253a47dc6bb"
    volume_uuid = "312dadca-c6c4-4e65-bea3-7b2f6ca819ee"
    volume_name = "test_restore"
    blockstore_uuid = "57c26b32-b3f3-4ceb-8a26-3c567d7d4166"

    create_volume = mocker.patch.object(service.VolmgrService, "create_volume",
                                        return_value=volume_uuid)
    add_volume = mocker.patch.object(service.VolmgrService,
                                     "add_volume_to_blockstore")
    mount_volume = mocker.patch.object(service.VolmgrService, "mount_volume")

    restore_snapshot = mocker.patch.object(service.VolmgrService,
                                           "restore_snapshot_from_blockstore")

    def post(req, resp):
        create_volume.assert_called_once()
        restore_snapshot.assert_called_once_with(snapshot_uuid,
                                                 old_volume_uuid,
                                                 volume_uuid,
                                                 blockstore_uuid)
        add_volume.assert_called(volume_uuid, blockstore_uuid)
        mount_path = os.path.join(CONFIG_OVERRIDE["VOLMGR_MOUNT_DIR"],
                                  volume_name,
                                  volume_uuid)
        mount_volume.assert_called(volume_uuid, mount_path, False,
                                   CONFIG_OVERRIDE[
                                       "VOLMGR_MOUNT_NAMESPACE_FD"])

        instance_data = resp['data']['instanceHostMap']['instance']['+data']
        inspect = instance_data['dockerInspect']

        assert len(inspect['Volumes']) == 1
        mpath = inspect['Volumes']['/opt']

        assert mpath is not None

        # Cannot use startswith because boot2docker link /tmp to /mnt/sda1/tmp
        # which result in docker volume mount shows in different path
        assert path.join(volmgr_mount, "default/test_restore",
                         volume_uuid) in mpath

        assert inspect['VolumesRW'] == {
            '/opt': True,
        }

        instance_activate_common_validation(resp)

    event_test(agent, 'docker/volmgr_instance_restore_volume', post_func=post)


@if_docker
def test_volmgr_delete_volume(agent, responses, mocker):
    # need to setup path for previous volume
    test_volmgr_instance_activate_volumes(agent, responses, mocker)

    volume_uuid = "0bcc6a7f-0c46-4d06-af51-224a47deeea8"
    volume_name = "test"

    data = '''{
        "Volumes": {
            "0bcc6a7f-0c46-4d06-af51-224a47deeea8": {
                "DevID": 2,
                "Size": 1073741824,
                "Snapshots": {
                    "ebf6ab98-8714-464e-8966-32f790b9d4ff": {
                        "DevID": 3
                    },
                    "c912c1f5-85d5-4488-9fbb-d58e876c44cc": {
                        "DevID": 4
                    },
                    "b2896c11-13e4-41d8-bd82-161ec113c381": {
                        "DevID": 5
                    }
                }
            }
        }
    }'''
    volume_response = json.loads(data)["Volumes"]
    mounted = mocker.patch.object(service, "mounted", return_value=True)
    list_volumes = mocker.patch.object(service.VolmgrService, "list_volumes",
                                       return_value=volume_response)
    delete_snapshot = mocker.patch.object(service.VolmgrService,
                                          "delete_snapshot")
    umount_volume = mocker.patch.object(service.VolmgrService,
                                        "umount_volume")
    delete_volume = mocker.patch.object(service.VolmgrService,
                                        "delete_volume")

    def post(req, resp):
        mounted.assert_called()
        list_volumes.assert_called_once_with(volume_uuid)
        dc1 = mock.call("ebf6ab98-8714-464e-8966-32f790b9d4ff", volume_uuid)
        dc2 = mock.call("c912c1f5-85d5-4488-9fbb-d58e876c44cc", volume_uuid)
        dc3 = mock.call("b2896c11-13e4-41d8-bd82-161ec113c381", volume_uuid)
        # json parse may reorder the entries
        delete_snapshot.assert_has_calls([dc1, dc2, dc3], any_order=True)
        umount_volume.assert_called_with(volume_uuid,
                                         CONFIG_OVERRIDE[
                                             "VOLMGR_MOUNT_NAMESPACE_FD"])
        delete_volume.assert_called_with(volume_uuid)
        assert not os.path.exists(path.join(
            CONFIG_OVERRIDE["VOLMGR_MOUNT_DIR"], volume_name))

    event_test(agent, 'docker/volmgr_volume_purge', post_func=post)


@if_docker
def test_volmgr_disabled(agent, responses, mocker):
    CONFIG_OVERRIDE["VOLMGR_ENABLED"] = "False"

    get_volume = mocker.patch.object(volmgr, "_get_volume")
    restore_snapshot = mocker.patch.object(volmgr, "_restore_snapshot")
    remove_volume = mocker.patch.object(volmgr, "remove_volume")

    def post(req, resp):
        get_volume.assert_not_called()
        restore_snapshot.assert_not_called()
        instance_activate_common_validation(resp)

    def post_vol(req, resp):
        remove_volume.assert_not_called()

    event_test(agent, 'docker/volmgr_instance_activate_volumes',
               post_func=post)
    event_test(agent, 'docker/volmgr_instance_restore_volume',
               post_func=post)
    event_test(agent, 'docker/volmgr_volume_purge', post_func=post_vol)
