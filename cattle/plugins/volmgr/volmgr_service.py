#!/usr/bin/python
import atexit

import subprocess
import json

import os


EXT4_FS = "ext4"


def register_loopback(data_file):
    # ideally we shouldn't have any leftover...
    output = subprocess.check_output(["losetup", "-j", data_file])
    if output == "":
        output = subprocess.check_output(["losetup", "-v", "-f",
                                          data_file])
        data_dev = output.strip().split(" ")[3]
    else:
        data_dev = output.split(":")[0].strip()
    atexit.register(cleanup_loopback, data_dev)
    assert data_dev.startswith("/dev/loop")
    return data_dev


def cleanup_loopback(dev):
    subprocess.call(["losetup", "-d", dev])


def create_pool_files(data_file, metadata_file):
    subprocess.check_call(["truncate", "-s", "100G", data_file])
    subprocess.check_call(["truncate", "-s", "5G", metadata_file])


def mounted(mount_dir, ns):
    output = subprocess.check_output(["volmgr_mount", ns, "-m"])
    if output.find(mount_dir) != -1:
        return True
    return False


class VolmgrService(object):
    def __init__(self, cmdline):
        self.base_cmdline = cmdline

    def init(self, driver, data_dev, metadata_dev, pool_name):
        subprocess.check_call(self.base_cmdline + [
            "init",
            "--driver", driver,
            "--driver-opts", "dm.datadev=" + data_dev,
            "--driver-opts", "dm.metadatadev=" + metadata_dev,
            "--driver-opts", "dm.thinpoolname=" + pool_name])

    def create_volume(self, size):
        data = subprocess.check_output(self.base_cmdline + [
            "volume", "create",
            "--size", str(size)])
        volume = json.loads(data)
        uuid = volume["UUID"]
        assert volume["Size"] == size
        return uuid

    def delete_volume(self, uuid):
        subprocess.check_call(self.base_cmdline + ["volume", "delete",
                                                   "--uuid", uuid])

    def mount_volume(self, uuid, path, need_format, ns):
        assert os.path.exists(path)
        cmdline = self.base_cmdline + ["volume", "mount",
                                       "--switch-ns", ns,
                                       "--uuid", uuid,
                                       "--mountpoint", path,
                                       "--fs", EXT4_FS]
        if need_format:
            cmdline = cmdline + ["--format"]

        subprocess.check_call(cmdline)

    def umount_volume(self, uuid, ns):
        cmdline = self.base_cmdline + ["volume", "umount",
                                       "--switch-ns", ns,
                                       "--uuid", uuid]
        subprocess.check_call(cmdline)

    def list_volumes(self, uuid=None):
        if uuid is None:
            data = subprocess.check_output(self.base_cmdline +
                                           ["volume", "list"])
            volumes = json.loads(data)
            return volumes

        data = subprocess.check_output(self.base_cmdline + ["volume", "list",
                                                            "--uuid", uuid])
        volumes = json.loads(data)
        return volumes

    def create_snapshot(self, volume_uuid):
        data = subprocess.check_output(self.base_cmdline +
                                       ["snapshot", "create",
                                        "--volume-uuid", volume_uuid])
        snapshot = json.loads(data)
        assert snapshot["VolumeUUID"] == volume_uuid
        return snapshot["UUID"]

    def delete_snapshot(self, snapshot_uuid, volume_uuid):
        subprocess.check_call(self.base_cmdline +
                              ["snapshot", "delete",
                               "--uuid", snapshot_uuid,
                               "--volume-uuid", volume_uuid])

    def register_vfs_blockstore(self, path):
        data = subprocess.check_output(self.base_cmdline +
                                       ["blockstore",
                                        "register", "--kind", "vfs",
                                        "--opts", "vfs.path=" + path])
        bs = json.loads(data)
        assert bs["Kind"] == "vfs"
        return bs["UUID"]

    def deregister_blockstore(self, uuid):
        subprocess.check_call(self.base_cmdline + ["blockstore", "deregister",
                                                   "--uuid", uuid])

    def add_volume_to_blockstore(self, volume_uuid, bs_uuid):
        subprocess.check_call(self.base_cmdline +
                              ["blockstore", "add",
                               "--volume-uuid", volume_uuid,
                               "--uuid", bs_uuid])

    def remove_volume_from_blockstore(self, volume_uuid, bs_uuid):
        subprocess.check_call(self.base_cmdline +
                              ["blockstore", "remove",
                               "--volume-uuid", volume_uuid,
                               "--uuid", bs_uuid])

    def backup_snapshot_to_blockstore(self, snapshot_uuid, volume_uuid,
                                      bs_uuid):
        subprocess.check_call(self.base_cmdline +
                              ["snapshot", "backup",
                               "--uuid", snapshot_uuid,
                               "--volume-uuid", volume_uuid,
                               "--blockstore-uuid", bs_uuid])

    def restore_snapshot_from_blockstore(self, snapshot_uuid,
                                         origin_volume_uuid,
                                         target_volume_uuid,
                                         bs_uuid):
        subprocess.check_call(self.base_cmdline +
                              ["snapshot", "restore",
                               "--uuid", snapshot_uuid,
                               "--origin-volume-uuid", origin_volume_uuid,
                               "--target-volume-uuid", target_volume_uuid,
                               "--blockstore-uuid", bs_uuid])

    def remove_snapshot_from_blockstore(self,
                                        snapshot_uuid, volume_uuid, bs_uuid):
        subprocess.check_call(self.base_cmdline +
                              ["snapshot", "remove",
                               "--uuid", snapshot_uuid,
                               "--volume-uuid", volume_uuid,
                               "--blockstore-uuid", bs_uuid])
