# LAMP Manager

A GTK4 application to manage your local PHP development stack on GNOME desktops. Start and stop Apache, Nginx, MySQL and PHP-FPM, create projects with their own `.test` domain, configure PHP and read the logs — all without touching the terminal.

> Designed for Ubuntu developers who work with Apache, MySQL and PHP-FPM on a daily basis.

---

## Features

- **Service control** — Start, stop, reload and restart Apache, Nginx, MySQL, PHP-FPM and Mailpit
- **`.test` virtual hosts** — Each project gets a `name.test` domain served by Apache (ports 80/443) and Nginx (8080/8443), with optional HTTPS through [mkcert](https://github.com/FiloSottile/mkcert)
- **Project creation** — Create plain PHP, Laravel, Symfony or WordPress projects; frameworks are configurable in `~/.config/lamp-manager/frameworks.json`
- **Unregistered folders** — Folders in your projects directory without a virtual host are detected and can be registered with one click
- **Safe changes** — Apache configuration is validated with `configtest` before reloading and reverted if invalid
- **Trash** — Deleted projects keep their configuration, files, database and certificates, and can be restored
- **MySQL** — Create and drop databases and users, and grant access
- **PHP** — Edit common `php.ini` parameters and enable or disable extensions
- **Apache modules** — Enable or disable modules, validated before applying
- **Log viewer** — Service and per-project logs with color-coded severity levels
- **Dashboard** — `http://localhost` lists your projects with their framework, git branch, size and recent errors
- **System tray** — Status icon (blue, orange or red), notifications when a service stops, minimize to tray and start at login
- **Mailpit integration** — Install and configure the [Mailpit](https://github.com/axllent/mailpit) email testing service
- **Recommendations** — Warns about recommended services that are not installed, with the command to install them

---

## Screenshots

### Services

![Services](screenshots/services.png)

### Virtual hosts

![Virtual hosts](screenshots/vhosts.png)

### PHP configuration

![PHP configuration](screenshots/phpconfig.png)

### PHP extensions

![PHP extensions](screenshots/phpextensions.png)

### Log viewer

![Apache error log](screenshots/apachelogerror.png)
![PHP log](screenshots/phplog.png)

---

## Requirements

- Ubuntu 26.04 (packages in the PPA are built for this release)
- Python 3.10 or later, GTK 4 and libadwaita
- `sudo` access (required to manage services and configuration files)

**Recommended services** (the application manages them, but does not require them to start):

- `apache2` and/or `nginx`
- `php-fpm` (any version from 8.0)
- `mysql-server` or `mariadb-server`
- `mkcert` for HTTPS, `composer` for Laravel and Symfony projects

---

## Installation

### Option 1 — PPA (recommended)

```bash
sudo add-apt-repository ppa:nefreyu-99/lamp-manager
sudo apt update
sudo apt install lamp-manager
```

### Option 2 — Download the .deb package

Download the latest `.deb` from the [Releases page](https://github.com/Nefreyu/lamp-manager/releases) and install it:

```bash
sudo apt install ./lamp-manager_*_all.deb
```

### Option 3 — Run from source

```bash
git clone https://github.com/Nefreyu/lamp-manager.git
cd lamp-manager

sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-secret-1 \
    gir1.2-dbusmenu-glib-0.4 gvfs-backends

python3 main.py
```

No pip packages are needed — the application relies entirely on system packages. When run from source, it installs its icons and launcher in `~/.local/share` so it shows up in the application menu.

---

## Usage

Launch LAMP Manager from your application menu or run:

```bash
lamp-manager              # open the window
lamp-manager --autostart  # start in the background, only in the system tray
```

On first launch the application asks for your administrator password. It is validated and stored in the GNOME Keyring so it is not requested again.

### Services tab

Each detected service shows its version, the ports it listens on and a switch to start or stop it. Services with a web interface (Apache, Nginx, phpMyAdmin, Mailpit) have a button to open it in the browser. If Apache is running but PHP-FPM is not, a banner offers to start it.

### Virtual hosts section

- **New project** — Choose a name and a framework; the name is converted to a valid domain (`My Project` → `my-project.test`). A database with the same name is created when MySQL is available.
- **Enable / disable** — Adds or removes the site in Apache, Nginx and `/etc/hosts`.
- **HTTPS** — Generates a trusted local certificate with mkcert.
- **Configuration** — Change the DocumentRoot (it must stay inside your projects directory), edit the Apache configuration and read the project logs.
- **Trash** — Moving a project to the trash disables it and keeps everything needed to restore it later.

The projects directory (`~/www` by default) and the Apache and Nginx ports can be changed in **Settings**.

---

## How it works

LAMP Manager uses the standard tools of your system:

- **systemd** (`systemctl`) — to start, stop and check services
- **a2ensite / a2enmod / phpenmod** — to manage Apache sites and modules and PHP extensions
- **apache2ctl configtest** — to validate the configuration before applying it
- **ss** — to detect the ports each service is listening on
- **sudo** — for privileged operations, using the password stored in the GNOME Keyring

While it is running, it checks the status of the services every 30 seconds to update the tray icon, and watches your projects directory and git branches to keep the dashboard up to date.

Settings are stored in `~/.config/lamp-manager/`, and the log, HTTPS certificates and trash in `~/.local/share/lamp-manager/`.

---

## Project structure

```text
lamp-manager/
├── main.py              # Entry point (Adw.Application)
├── config/              # Settings, logging and version
├── windows/             # Main window, password dialog and splash screen
├── pages/               # One page per section: services, virtual hosts, settings…
├── services/            # Logic: systemd, Apache, Nginx, MySQL, PHP, vhosts, hosts, tray…
├── tests/               # pytest test suite
├── data/                # AppStream metainfo and man page
├── packaging/           # .desktop file and icons
└── debian/              # Debian packaging
```

---

## Development

The tests use pytest. Create a virtual environment with access to the system GTK bindings and run them:

```bash
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

To build the Debian package (requires `debhelper`):

```bash
dpkg-buildpackage -us -uc -b
```

The `.deb` is created in the parent directory.

---

## Contributing

Contributions are welcome:

1. Fork the repository
2. Create a branch: `git checkout -b my-feature`
3. Make your changes, add tests where possible and run the test suite
4. Open a pull request

Changes that touch services or system files should also be tested manually against a real LAMP environment.

---

## License

LAMP Manager is free software released under the [GNU General Public License v3.0](LICENSE).

Copyright © 2026 Juan Diez
