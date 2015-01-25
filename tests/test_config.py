from cattle import default_value, Config
import uuid
import os


def test_default_value():
    # evn var is unset, return default
    var_name = uuid.uuid4().hex
    cattlefied_var_name = 'CATTLE_{}'.format(var_name)
    default = 'defaulted'
    actual = default_value(var_name, default)
    assert default == actual

    # default is explicitly blank, return blank
    actual = default_value(var_name, '')
    assert '' == actual

    # env var is set to blank, return default
    os.environ[cattlefied_var_name] = ''
    actual = default_value(var_name, default)
    assert default == actual

    # env var is set, return env var value
    os.environ[cattlefied_var_name] = 'foobar'
    actual = default_value(var_name, default)
    assert 'foobar' == actual

    # for completeness, set_secret_key which hits the CONFIG_OVERRIDE
    # code path
    Config.set_secret_key('override')
    actual = default_value('SECRET_KEY', default)
    assert 'override' == actual
