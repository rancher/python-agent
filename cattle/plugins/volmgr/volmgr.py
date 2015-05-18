import logging
import shutil
from cattle.plugins.volmgr import service

import os
import os.path
from cattle import Config
from .service import VolmgrService


log = logging.getLogger("volmgr")

RANCHER_PREFIX = "/rancher/"
INSTANCE_TAG_FILE = "instance"

v = VolmgrService("")
blockstore_uuid = ""


def enabled():
    return Config.volmgr_enabled().lower() == "true"


def _get_volume_dir(vol_name, user):
    return os.path.join(Config.volmgr_mount_dir(), user, vol_name)


def _get_volume_uuid(path):
    filelist = os.listdir(path)
    volume_uuid = ""
    for i in filelist:
        if i == INSTANCE_TAG_FILE:
            continue
        volume_uuid = i
    return volume_uuid


def _get_volume_instance_name(path):
    old_instance_file = open(os.path.join(path, INSTANCE_TAG_FILE), "r")
    old_instance_name = ""
    try:
        old_instance_name = old_instance_file.read()
    finally:
        old_instance_file.close()
    return old_instance_name


def _get_volume(vol_name, vol_size, instance_name, user):
    path = _get_volume_dir(vol_name, user)
    if os.path.exists(path):
        volume_uuid = _get_volume_uuid(path)
        create = False
        if volume_uuid == "":
            log.warning("Found volume directory but cannot find related \
                    volume! Create one")
            create = True

        assert _get_volume_instance_name(path) == instance_name

        if not create:
            mount_dir = os.path.join(path, volume_uuid)
            if not service.mounted(mount_dir,
                                   Config.volmgr_mount_namespace_fd()):
                v.mount_volume(volume_uuid, mount_dir, False,
                               Config.volmgr_mount_namespace_fd())
            return mount_dir

    volume_uuid = v.create_volume(vol_size)
    v.add_volume_to_blockstore(volume_uuid, blockstore_uuid)
    mount_dir = os.path.join(path, volume_uuid)
    os.makedirs(mount_dir)
    f = open(os.path.join(path, INSTANCE_TAG_FILE), "w")
    try:
        f.write(instance_name)
    finally:
        f.close()
    v.mount_volume(volume_uuid, mount_dir, True,
                   Config.volmgr_mount_namespace_fd())
    return mount_dir


def volume_exists(path):
    if not enabled():
        return False
    if not path.startswith(Config.volmgr_mount_dir()):
        return False
    if not os.path.exists(path):
        return False
    return service.mounted(path, Config.volmgr_mount_namespace_fd())


def remove_internal_snapshots_for_volume(volume_uuid):
    log.info("Removing snapshots for volume %s" % volume_uuid)
    volume = v.list_volumes(volume_uuid)[volume_uuid]
    snapshots = volume["Snapshots"]
    for s in snapshots:
        v.delete_snapshot(s, volume_uuid)


def cleanup_internal_snapshots(latest_snapshots_set,
                               volume_uuid,
                               blockstore_uuid):
    snapshots = v.list_volumes(volume_uuid)[volume_uuid]["Snapshots"]
    for snapshot_uuid in snapshots:
        if snapshot_uuid not in latest_snapshots_set:
            # Don't cleanup if it's not backed up yet
            if snapshot_exists_in_blockstore(snapshot_uuid,
                                             volume_uuid,
                                             blockstore_uuid):
                log.info("Removing snapshot %s for volume %s" % (
                    snapshot_uuid, volume_uuid))
                v.delete_snapshot(snapshot_uuid, volume_uuid)


def remove_volume(path):
    if not enabled():
        return
    if not volume_exists(path):
        return
    volume_name_path = path.rsplit('/', 1)[0]
    volume_uuid = path.rsplit('/', 1)[1]
    log.info("Removing volume %s for instance %s" % (
             volume_uuid, _get_volume_instance_name(volume_name_path)))
    remove_internal_snapshots_for_volume(volume_uuid)
    v.umount_volume(volume_uuid, Config.volmgr_mount_namespace_fd())
    v.delete_volume(volume_uuid)
    shutil.rmtree(volume_name_path)
    log.info("Cleaned volume %s's mount directory at %s" % (
             volume_uuid, volume_name_path))


def create_snapshot(vol_uuid, snapshot_uuid):
    return v.create_snapshot(vol_uuid, snapshot_uuid)


def backup_snapshot(snapshot_uuid, vol_uuid, blockstore_uuid):
    v.backup_snapshot_to_blockstore(snapshot_uuid, vol_uuid, blockstore_uuid)


def remove_snapshot_from_blockstore(snapshot_uuid, vol_uuid, blockstore_uuid):
    v.remove_snapshot_from_blockstore(snapshot_uuid, vol_uuid,
                                      blockstore_uuid)


def delete_snapshot(snapshot_uuid, vol_uuid):
    v.delete_snapshot(snapshot_uuid, vol_uuid)


def _restore_snapshot(vol_name, old_volume_uuid, vol_size,
                      snapshot_uuid, instance_name, user):
    path = _get_volume_dir(vol_name, user)
    if os.path.exists(path):
        log.info("Already found the volume, skip restore")
        volume_uuid = _get_volume_uuid(path)
        return os.path.join(path, volume_uuid)
    volume_uuid = v.create_volume(vol_size)
    v.restore_snapshot_from_blockstore(snapshot_uuid, old_volume_uuid,
                                       volume_uuid, blockstore_uuid)
    v.add_volume_to_blockstore(volume_uuid, blockstore_uuid)

    mount_dir = os.path.join(path, volume_uuid)
    os.makedirs(mount_dir)
    f = open(os.path.join(path, INSTANCE_TAG_FILE), "w")
    try:
        f.write(instance_name)
    finally:
        f.close()
    v.mount_volume(volume_uuid, mount_dir, False,
                   Config.volmgr_mount_namespace_fd())
    return mount_dir


def update_managed_volume(instance, config, start_config):
    if not enabled():
        return
    if 'binds' not in start_config:
        return
    binds_map = start_config['binds']
    instance_name = config['name']
    new_binds_map = {}
    user = "default"
    if 'user' in config and config['user'] is not None:
        user = config['user']
    for bind in binds_map:
        src = bind
        dst = binds_map[bind]
        if src.startswith(RANCHER_PREFIX):
            vol_command = src[len(RANCHER_PREFIX):]
            words = vol_command.split("/")
            vol_name = words[0]
            command = ""
            old_volume_uuid = ""
            snapshot_uuid = ""
            if len(words) > 1:
                command = words[1]
                if command == "restore":
                    assert len(words) == 4
                    old_volume_uuid = words[2]
                    snapshot_uuid = words[3]
                else:
                    log.error("unsupported command %s, \
                              ignore and create volume", command)

            if command == "restore":
                log.info("About to restore snapshot")
                mount_point = _restore_snapshot(
                    vol_name, old_volume_uuid,
                    Config.volmgr_default_volume_size(), snapshot_uuid,
                    instance_name, user)
                new_binds_map[mount_point] = dst
            else:
                mount_point = _get_volume(vol_name,
                                          Config.volmgr_default_volume_size(),
                                          instance_name, user)
                new_binds_map[mount_point] = dst
        else:
            new_binds_map[src] = binds_map[src]
    start_config['binds'] = new_binds_map


def snapshot_exists_internally(snapshot_uuid, volume_uuid):
    volumes = v.check_snapshot(snapshot_uuid, volume_uuid)
    if volume_uuid not in volumes:
        return False
    return snapshot_uuid in volumes[volume_uuid]["Snapshots"]


def snapshot_exists_in_blockstore(snapshot_uuid, volume_uuid, blockstore_uuid):
    volumes = v.check_snapshot_from_blockstore(snapshot_uuid,
                                               volume_uuid,
                                               blockstore_uuid)
    if volume_uuid not in volumes:
        return False
    return snapshot_uuid in volumes[volume_uuid]["Snapshots"]


class Volmgr(object):
    def on_startup(self):
        if not enabled():
            return
        log.info("Volmgr enabled")
        driver = Config.volmgr_storage_driver()
        if driver != "devicemapper":
            raise Exception("Unknown volmgr driver %s" % (driver))

        data_dev = Config.volmgr_dm_data_device()
        metadata_dev = Config.volmgr_dm_metadata_device()
        if data_dev != "" and metadata_dev != "":
            if os.path.exists(data_dev) and os.path.exists(metadata_dev):
                raise Exception("Provided data_dev %s and metadata_dev %s, \
                        but unable to find the devices" % (
                    data_dev, metadata_dev))
        elif (data_dev == "") ^ (metadata_dev == ""):
            raise Exception("Only one of two device mapper devices \
                    are specified")

        data_file = Config.volmgr_dm_data_file()
        metadata_file = Config.volmgr_dm_metadata_file()

        if os.path.exists(data_file) and os.path.exists(metadata_file):
            log.info("Found existed device mapper data and metadata file,"
                     "load them to loopback device")
        elif not (os.path.exists(data_file) or os.path.exists(metadata_file)):
            log.info("Existed device mapper data and metadata file not found, "
                     "create them")
            service.create_pool_files(data_file, metadata_file)
        else:
            raise Exception("Only one of data or metadata file exists, "
                            "please clean up %s ,%s" % (data_file,
                                                        metadata_file))

        if data_dev == "":
            data_dev = service.register_loopback(data_file)
            log.info("Loaded %s to %s" % (data_file, data_dev))
            metadata_dev = service.register_loopback(metadata_file)
            log.info("Loaded %s to %s" % (metadata_file, metadata_dev))

        root_dir = Config.volmgr_root()
        mount_dir = Config.volmgr_mount_dir()
        if not os.path.exists(root_dir):
            os.makedirs(root_dir)
        log.info("Root_dir for volmgr at %s " % root_dir)
        if not os.path.exists(mount_dir):
            os.makedirs(mount_dir)
        log.info("Mount_dir for volmgr at %s " % mount_dir)

        base_cmdline = ["volmgr", "--debug",
                        "--log", Config.volmgr_log_file(),
                        "--root", root_dir]
        global v
        v = VolmgrService(base_cmdline)
        pool_name = Config.volmgr_pool_name()
        # TODO better for volmgr to verify cfg is the same
        if not os.path.exists(os.path.join(root_dir, "volmgr.cfg")):
            v.init(driver, data_dev, metadata_dev, pool_name)
        log.info("Complete init for volmgr, init pool %s" % pool_name)

        global blockstore_uuid
        if not os.path.exists(Config.volmgr_blockstore_dir()):
            os.makedirs(Config.volmgr_blockstore_dir())
        blockstore_uuid = v.register_vfs_blockstore(
            Config.volmgr_blockstore_dir())
        log.info("Complete register blockstore for volmgr at %s, uuid %s" % (
                 Config.volmgr_blockstore_dir(), blockstore_uuid))
