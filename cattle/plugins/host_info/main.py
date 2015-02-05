import logging

from cattle.plugins.host_info.memory import MemoryCollector
from cattle.plugins.host_info.os_c import OSCollector
from cattle.plugins.host_info.cpu import CpuCollector
from cattle.plugins.host_info.disk import DiskCollector

log = logging.getLogger('host_info')


class HostInfo(object):
    def __init__(self):
        self.collectors = [MemoryCollector(),
                           OSCollector(),
                           DiskCollector(),
                           CpuCollector()]

    def collect_data(self):
        data = {}
        for collector in self.collectors:
            try:
                data[collector.key_name()] = collector.get_data()
            except:
                log.exeception(
                    "Error collecting {0} stats".format(collector.key_name()))
                data[collector.key_name()] = {}

        return data
