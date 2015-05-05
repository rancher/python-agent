import json

import mock
from .common_fixtures import *  # NOQA
from .docker_common import *  # NOQA
from cattle import CONFIG_OVERRIDE
from cattle.plugins.volmgr import volmgr, service, Volmgr
from os import path
import os


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
    delete_container('/c-c861f990-4472-4fa1-960f-65171b544c28')

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

    def pre(req):
        req["data"]["snapshot"]["uuid"] = snapshot_uuid

    def post(req, resp):
        create_snapshot.assert_called_once_with(volume_uuid,
                                                snapshot_uuid)
        snapshot = resp["data"]["snapshot"]
        assert snapshot["+data"]["+fields"]["managedSnapshotUUID"] == \
            snapshot_uuid
        assert snapshot["+data"]["+fields"]["managedVolumeUUID"] == \
            volume_uuid
        del resp["data"]["snapshot"]["+data"]

    event_test(agent, 'docker/volmgr_snapshot_create',
               pre_func=pre,
               post_func=post)


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
        snapshot["uuid"] = snapshot_uuid
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
        snapshot["uuid"] = snapshot_uuid
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

    delete_container("c-5f7d6bf1-0528-439d-abca-49daf59002aa")

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
