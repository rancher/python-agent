from .common_fixtures import *  # NOQA
from .docker_common import *  # NOQA


@if_docker
def test_network_mode_none(agent, responses):
    delete_container('/c861f990-4472-4fa1-960f-65171b544c28')

    def pre(req):
        instance = req['data']['instanceHostMap']['instance']
        instance['nics'][0]['network']['kind'] = 'dockerNone'

    def post(req, resp):
        instance_data = resp['data']['instanceHostMap']['instance']['+data']
        docker_inspect = instance_data['dockerInspect']
        assert docker_inspect['Config']['NetworkDisabled']

    event_test(agent, 'docker/instance_activate', pre_func=pre,
               post_func=post, no_diff=True)


@if_docker
def test_network_mode_host(agent, responses):
    delete_container('/c861f990-4472-4fa1-960f-65171b544c28')

    def pre(req):
        instance = req['data']['instanceHostMap']['instance']
        instance['nics'][0]['network']['kind'] = 'dockerHost'

    def post(req, resp):
        instance_data = resp['data']['instanceHostMap']['instance']['+data']
        docker_inspect = instance_data['dockerInspect']
        assert not docker_inspect['Config']['NetworkDisabled']
        assert docker_inspect['HostConfig']['NetworkMode'] == 'host'

    event_test(agent, 'docker/instance_activate', pre_func=pre,
               post_func=post, no_diff=True)


@if_docker
def test_network_mode_container(agent, responses):
    delete_container('/network-container')
    delete_container('/c861f990-4472-4fa1-960f-65171b544c28')

    client = docker_client()
    c = client.create_container('ibuildthecloud/helloworld',
                                name='network-container')
    client.start(c)

    def pre(req):
        instance = req['data']['instanceHostMap']['instance']
        instance['nics'][0]['network']['kind'] = 'dockerContainer'
        instance['networkContainer'] = JsonObject({
            'uuid': 'network-container'
        })

    def post(req, resp):
        instance_data = resp['data']['instanceHostMap']['instance']['+data']
        docker_inspect = instance_data['dockerInspect']
        assert not docker_inspect['Config']['NetworkDisabled']
        assert docker_inspect['HostConfig']['NetworkMode'] == \
            'container:{}'.format(c['Id'])

    event_test(agent, 'docker/instance_activate', pre_func=pre,
               post_func=post, no_diff=True)
