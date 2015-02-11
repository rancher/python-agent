import pytest
from cattle.utils import CadvisorAPIClient


@pytest.fixture
def cadvisor_client():
    return CadvisorAPIClient('127.0.0.1', '9344')


def test_cadvisor_time(cadvisor_client):
    time_vals = {"2015-02-04T23:21:38.251266323-07:00":
                 "2015-01-28T20:08:16.967019892Z",
                 "2015-02-04T23:21:38.251266323+07:00":
                 "2015-01-28T20:08:16.967019892Z",
                 }

    for time_val_key in time_vals.keys():
        val = cadvisor_client.timestamp_diff(time_val_key,
                                             time_vals[time_val_key])
        assert type(val) == float
