import platform

from cattle.utils import CadvisorAPIClient
from cattle import Config


class DiskCollector(object):
    def __init__(self):
        self.unit = 1048576
        self.cadvisor = CadvisorAPIClient(Config.cadvisor_ip(),
                                          Config.cadvisor_port())

    def _convert_units(self, number):
        # Return in MB
        return round(float(number)/self.unit, 3)

    def _get_mountpoints_cadvisor(self):
        data = {}
        stat = self.cadvisor.get_latest_stat()

        if 'filesystem' in stat.keys():
            for fs in stat['filesystem']:
                device = fs['device']
                percent_used = float(fs['usage']) / float(fs['capacity']) * 100

                data[device] = {
                    'free': self._convert_units(fs['capacity'] - fs['usage']),
                    'total': self._convert_units(fs['capacity']),
                    'used': self._convert_units(fs['usage']),
                    'percentUsed': round(percent_used, 2)
                }

        return data

    def _get_machine_filesystems_cadvisor(self):
        data = {}
        machine_info = self.cadvisor.get_machine_stats()

        if 'filesystems' in machine_info.keys():
            for filesystem in machine_info['filesystems']:
                data[filesystem['device']] = {
                    'capacity': self._convert_units(filesystem['capacity'])
                }

        return data

    def key_name(self):
        return 'diskInfo'

    def get_data(self):
        data = {
            'fileSystems': {},
            'mountPoints': {}
        }

        if platform.system() == 'Linux':
            data['fileSystems'].update(
                self._get_machine_filesystems_cadvisor())
            data['mountPoints'].update(self._get_mountpoints_cadvisor())

        return data
