{ pkgs ? import <nixpkgs> {} }:
let
  my-python = pkgs.python310;
  python-with-my-packages = my-python.withPackages (p: with p; [
    pip
    django-auth-ldap
    poetry
    cryptography

    # other python packages you want
  ]);
in
pkgs.mkShell {
  buildInputs = [
    python-with-my-packages
    # other dependencies
  ];
  shellHook = ''
    PYTHONPATH=${python-with-my-packages}/${python-with-my-packages.sitePackages}
    # maybe set more env-vars
    NAUTOBOT_ALLOWED_HOSTS=*
    NAUTOBOT_CHANGELOG_RETENTION=0
    NAUTOBOT_CONFIG=/opt/nautobot/nautobot_config.py
    # If using MySQL, set NAUTOBOT_DB_HOST=mysql
    NAUTOBOT_DB_HOST=postgres
    NAUTOBOT_DB_NAME=nautobot
    NAUTOBOT_DB_PASSWORD=decinablesprewad
    NAUTOBOT_DB_USER=nautobot
    NAUTOBOT_DB_TIMEOUT=300
    # If using MySQL, set NAUTOBOT_DB_ENGINE=django.db.backends.mysql
    NAUTOBOT_DB_ENGINE=django.db.backends.postgresql
    NAUTOBOT_NAPALM_TIMEOUT=5
    NAUTOBOT_REDIS_HOST=redis
    NAUTOBOT_REDIS_PASSWORD=decinablesprewad
    NAUTOBOT_REDIS_PORT=6379
    # Uncomment REDIS_SSL if using SSL
    # NAUTOBOT_REDIS_SSL=True
    NAUTOBOT_SECRET_KEY=012345678901234567890123456789012345678901234567890123456789

    # Needed for MySQL, must match the values for Nautobot above
    MYSQL_ROOT_PASSWORD=decinablesprewad
    MYSQL_DATABASE=nautobot
    MYSQL_PASSWORD=decinablesprewad
    MYSQL_USER=nautobot

    # Needed for Postgres, must match the values for Nautobot above
    PGPASSWORD=decinablesprewad
    POSTGRES_DB=nautobot
    POSTGRES_PASSWORD=decinablesprewad
    POSTGRES_USER=nautobot

    # Needed for Redis, must match the values for Nautobot above
    REDIS_PASSWORD=decinablesprewad

    # Needed for Selenium integration tests
    NAUTOBOT_SELENIUM_URL=http://selenium:4444/wd/hub  # WebDriver (Selenium client)
    NAUTOBOT_SELENIUM_HOST=nautobot  # LiveServer (Nautobot server)

    # Allow self signed git repositories for config contexts, export templates, ...
    # GIT_SSL_NO_VERIFY="1"

    NAUTOBOT_BLUECAT_URL="https://proteus.server.utsc.utoronto.ca"
    NAUTOBOT_BLUECAT_USERNAME="netapi"
    NAUTOBOT_BLUECAT_PASSWORD_CMD="pass utsc/bluecat | head -n1"

    NAUTOBOT_CREATE_SUPERUSER=true
    NAUTOBOT_SUPERUSER_NAME=admin
    NAUTOBOT_SUPERUSER_EMAIL=admin@example.com
    NAUTOBOT_SUPERUSER_PASSWORD=admin
    NAUTOBOT_SUPERUSER_API_TOKEN=0123456789abcdef0123456789abcdef01234567
  '';
}