from dynaconf import Dynaconf

settings = Dynaconf(
    envvar_prefix="ANDREWBOT",
    settings_files=['.secrets.toml', 'settings.toml'],
)

# `envvar_prefix` = export envvars with `export DYNACONF_FOO=bar`.
# `settings_files` = Load this files in the order.
