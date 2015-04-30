import logging
from cattle import Config
from cattle.agent.handler import BaseHandler
from cattle.progress import Progress

from . import volmgr

log = logging.getLogger('volmgr')


class SnapshotHandler(BaseHandler):
    def __init__(self):
        super(SnapshotHandler, self).__init__()

    def _get_handler_category(self, req):
        return "storage"

    def _check_supports(self, req):
        return True

    def snapshot_create(self, req=None, snapshot=None, **kw):
        progress = Progress(req)

        return self._do(
            req=req,
            check=lambda: self._is_snapshot_created(snapshot),
            result=lambda: self._get_response_data(req, snapshot),
            lock_obj=snapshot,
            action=lambda: self._do_snapshot_create(snapshot, progress)
        )

    def snapshot_backup(self, req=None, snapshotStoragePoolMap=None, **kw):
        snapshot = snapshotStoragePoolMap.snapshot
        storage_pool = snapshotStoragePoolMap.storagePool
        progress = Progress(req)

        return self._do(
            req=req,
            check=lambda: self._is_snapshot_backed_up(snapshot, storage_pool),
            result=lambda: self._get_response_data(
                req, snapshotStoragePoolMap),
            lock_obj=snapshot,
            action=lambda: self._do_snapshot_backup(
                snapshot, storage_pool, progress)
        )

    def snapshot_remove(self, req=None, snapshotStoragePoolMap=None, **kw):
        snapshot = snapshotStoragePoolMap.snapshot
        storage_pool = snapshotStoragePoolMap.storagePool
        progress = Progress(req)

        return self._do(
            req=req,
            check=lambda: self._is_snapshot_removed(snapshot, storage_pool),
            result=lambda: self._get_response_data(
                req, snapshotStoragePoolMap),
            lock_obj=snapshot,
            action=lambda: self._do_snapshot_remove(
                snapshot, storage_pool, progress)
        )

    def _is_snapshot_created(self, snapshot):
        return 'snapshotUUID' in snapshot.data.fields

    def _do_snapshot_create(self, snapshot, progress):
        log.info("Creating snapshot")
        volume_uri = snapshot.volume.uri
        local_uri = volume_uri.split(Config.volmgr_mount_dir())[1]
        volume_uuid = local_uri.rsplit('/', 1)[1]
        log.info("Creating snapshot for volume %s" % volume_uuid)
        snapshot_uuid = volmgr.create_snapshot(volume_uuid)
        snapshot.data.fields['snapshotUUID'] = snapshot_uuid
        snapshot.data.fields['volumeUUID'] = volume_uuid
        log.info("New snapshot for volume, uuid is %s" % snapshot_uuid)
        return True

    def _is_snapshot_backed_up(self, snapshot, storage_pool):
        return 'backup' in snapshot.data.fields

    def _do_snapshot_backup(self, snapshot, storage_pool, progress):
        snapshot_uuid = snapshot.data.fields['snapshotUUID']
        volume_uri = snapshot.volume.uri
        local_uri = volume_uri.split(Config.volmgr_mount_dir())[1]
        volume_uuid = local_uri.rsplit('/', 1)[1]
        log.info("Backing up snapshot %s for volume %s" % (
            snapshot_uuid, volume_uuid))
        volmgr.backup_snapshot(snapshot_uuid, volume_uuid)
        log.info("Backed up snapshot %s for volume %s" % (
            snapshot_uuid, volume_uuid))
        snapshot.data.fields['backup'] = True
        return True

    def _is_snapshot_removed(self, snapshot, storage_pool):
        return 'removed' in snapshot.data.fields

    def _do_snapshot_remove(self, snapshot, storage_pool, progress):
        volume_uuid = snapshot.data.fields['volumeUUID']
        snapshot_uuid = snapshot.data.fields['snapshotUUID']
        log.info("Removing snapshot %s for volume %s" % (
            snapshot_uuid, volume_uuid))
        volmgr.remove_snapshot_from_blockstore(snapshot_uuid, volume_uuid)
        volmgr.delete_snapshot(snapshot_uuid, volume_uuid)
        log.info("Removed snapshot %s for volume %s" % (
            snapshot_uuid, volume_uuid))
        snapshot.data.fields['removed'] = True
        return True

    def _get_snapshot_data(self, obj):
        snapshot = obj
        return {
            '+data': {
                '+fields': {
                    'snapshotUUID': snapshot.data.fields['snapshotUUID'],
                }
            }
        }
