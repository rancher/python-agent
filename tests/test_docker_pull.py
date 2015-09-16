from .common_fixtures import *  # NOQA
from .docker_common import *  # NOQA

from docker.errors import APIError


@if_docker
def test_pull(agent, responses):
    client = docker_client()
    try:
        client.remove_image('tianon/true:latestrandom', force=True)
    except:
        pass

    def post(req, resp):
        inspect = client.inspect_image('tianon/true:latest')
        assert resp.data.fields.dockerImage.Id == inspect['Id']
        resp.data.fields.dockerImage = {}

    event_test(agent, 'docker/instance_pull', post_func=post, diff=True)

    inspect = client.inspect_image('tianon/true:latestrandom')
    assert inspect is not None

    def pre2(req):
        req.data.instancePull.complete = True

    def post2(req, resp):
        assert resp.data == {}

    event_test(agent, 'docker/instance_pull', pre_func=pre2,  post_func=post2,
               diff=False)

    with pytest.raises(APIError):
        client.inspect_image('tianon/true:latestrandom')


@if_docker
def test_pull_mode_update(agent, responses):
    client = docker_client()

    with pytest.raises(APIError):
        client.inspect_image('garbage')

    def pre(req):
        req.data.instancePull.image.data.dockerImage.fullName = 'garbage'
        req.data.instancePull.mode = 'cached'

    def post(req, resp):
        assert resp.data == {}

    event_test(agent, 'docker/instance_pull', pre_func=pre,  post_func=post,
               diff=False)
