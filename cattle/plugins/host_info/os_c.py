import platform


class OSCollector(object):
    def __init__(self, docker_client=None):
        self.docker_client = docker_client

    def key_name(self):
        return "osInfo"

    def _zip_fields_values(self, keys, values):
        data = {}
        for key, value in zip(keys, values):
            if len(value) > 0:
                data[key] = value
            else:
                data[key] = None

        return data

    def _get_docker_version(self):
        data = {}

        if platform.system() == 'Linux':
            version = "Unknown"
            if self.docker_client:
                ver_resp = self.docker_client.version()
                version = "Docker version {0}, build {1}".format(
                    ver_resp.get("Version", "Unknown"),
                    ver_resp.get("GitCommit", "Unknown"))

            data['dockerVersion'] = version

        return data

    def _get_os(self):
        data = {}
        if platform.system() == 'Linux':
            if self.docker_client:
                data["operatingSystem"] = \
                    self.docker_client.info().get("OperatingSystem",
                                                  None)

            data['kernelVersion'] = \
                platform.release() if len(platform.release()) > 0 else None

        return data

    def get_data(self):
        data = self._get_os()
        data.update(self._get_docker_version())

        return data
