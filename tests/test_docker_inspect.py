from .common_fixtures import *  # NOQA
from .docker_common import *  # NOQA


@if_docker
def test_inspect_by_name(agent, responses):
    delete_container('/inspect_test')

    client = docker_client()
    c = client.create_container('ibuildthecloud/helloworld',
                                name='inspect_test')
    inspect = docker_client().inspect_container(c['Id'])

    def post(req, resp):
        response_inspect = resp['data']['instanceInspect']
        diff_dict(inspect, response_inspect)

    event_test(agent, 'docker/instance_inspect',
               post_func=post, diff=False)


@if_docker
def test_inspect_by_id(agent, responses):
    delete_container('/inspect_test')

    client = docker_client()
    c = client.create_container('ibuildthecloud/helloworld',
                                name='inspect_test')
    inspect = docker_client().inspect_container(c['Id'])

    def pre(req):
        instance_inspect = req['data']['instanceInspect']
        instance_inspect['id'] = c['Id']
        del instance_inspect['name']

    def post(req, resp):
        response_inspect = resp['data']['instanceInspect']
        diff_dict(inspect, response_inspect)

    event_test(agent, 'docker/instance_inspect', pre_func=pre,
               post_func=post, diff=False)


@if_docker
def test_inspect_not_found(agent, responses):
    delete_container('/inspect_test')

    def post(req, resp):
        assert resp['data']['instanceInspect'] is None

    event_test(agent, 'docker/instance_inspect', post_func=post, diff=False)
