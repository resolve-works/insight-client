import logging
from pathlib import Path
from os import environ as env
from configparser import ConfigParser

logging.basicConfig(level=logging.ERROR)

xdg_config_home = env.get("XDG_CONFIG_HOME", Path.home() / ".config")
config_file = xdg_config_home / "insight.conf"

config = ConfigParser()
try:
    config.read(config_file)
except Exception as e:
    logging.error(e)

keys = [
    ("api", "endpoint"),
    ("oidc", "endpoint"),
    ("oidc", "client-id"),
    ("oidc", "client-secret"),
    ("storage", "sts-endpoint"),
    ("storage", "identity-role"),
    ("storage", "endpoint"),
    ("storage", "bucket"),
    ("storage", "region"),
]


def environment_variable(section, option: str):
    return f"INSIGHT_{section}_{option.replace('-', '_')}".upper()


# Load environment into config
for section, option in keys:
    key = environment_variable(section, option)
    if env.get(key) is not None:
        config.set(section, option, env.get(key))


# Let user know config is missing when CLI is used without config present
def get_option(section, option):
    try:
        return config.get(section, option)
    except Exception:
        key = environment_variable(section, option)
        logging.error(
            f"Config option {section}.{option} not found and {key} not set in environment."
        )
        logging.error(f"Configure with `insight configure` or set {key}")
        exit(1)
