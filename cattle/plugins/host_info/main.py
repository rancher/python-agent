from cattle.plugins.host_info.memory import MemoryCollector
from cattle.plugins.host_info.os_c import OSCollector
from cattle.plugins.host_info.cpu import CpuCollector
from cattle.plugins.host_info.disk import DiskCollector


class HostInfo(object):
    def __init__(self):
        self.collectors = [MemoryCollector(),
                           OSCollector(),
                           DiskCollector(),
                           CpuCollector()]

    def collect_data(self):
        data = {}
        for collector in self.collectors:
            data[collector.key_name()] = collector.get_data()

        return data
