#!/bin/bash
set -e

VERSION="0.1.0"
PKG_NAME="lamp-manager"
ARCH="all"
MAINTAINER="Juan Diez <nefreyu.99@gmail.com>"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
OUTPUT_DIR="$PROJECT_DIR"
BUILD_DIR="$(mktemp -d)"
PKG_DIR="$BUILD_DIR/${PKG_NAME}_${VERSION}_${ARCH}"

echo "Construyendo $PKG_NAME $VERSION..."

# Estructura de directorios
mkdir -p "$PKG_DIR/DEBIAN"
mkdir -p "$PKG_DIR/usr/bin"
mkdir -p "$PKG_DIR/usr/lib/lamp-manager"
mkdir -p "$PKG_DIR/usr/share/applications"
mkdir -p "$PKG_DIR/usr/share/icons/hicolor/scalable/apps"

# Copiar fuentes (excluir archivos de desarrollo y cachés)
rsync -a \
  --exclude='config/dev.py' \
  --exclude='config/__pycache__' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.git' \
  --exclude='packaging' \
  "$PROJECT_DIR/" "$PKG_DIR/usr/lib/lamp-manager/"

# Launcher ejecutable
cat > "$PKG_DIR/usr/bin/lamp-manager" << 'LAUNCHER'
#!/bin/bash
exec python3 /usr/lib/lamp-manager/main.py "$@"
LAUNCHER
chmod 755 "$PKG_DIR/usr/bin/lamp-manager"

# Archivos de escritorio e icono
cp "$SCRIPT_DIR/io.github.nefreyu.LampManager.desktop" "$PKG_DIR/usr/share/applications/"
cp "$SCRIPT_DIR/icons/hicolor/scalable/apps/io.github.nefreyu.LampManager.svg" "$PKG_DIR/usr/share/icons/hicolor/scalable/apps/"

# DEBIAN/control
cat > "$PKG_DIR/DEBIAN/control" << EOF
Package: $PKG_NAME
Version: $VERSION
Section: admin
Priority: optional
Architecture: $ARCH
Depends: python3 (>= 3.10), python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1, gvfs-backends, sudo
Maintainer: $MAINTAINER
Description: LAMP stack manager for GNOME
 GTK4 application to manage Apache, MySQL, PHP-FPM and related
 services in a GNOME desktop environment.
EOF

# DEBIAN/postinst
cat > "$PKG_DIR/DEBIAN/postinst" << 'POSTINST'
#!/bin/bash
set -e
if command -v update-desktop-database > /dev/null; then
    update-desktop-database /usr/share/applications
fi
if command -v gtk-update-icon-cache > /dev/null; then
    gtk-update-icon-cache -f /usr/share/icons/hicolor
fi

cat > /dev/tty << 'MSG'

LAMP Manager instalado.
Esta aplicación requiere Apache, PHP-FPM y un servidor de base de datos
para tener utilidad. Instálalos con:

  sudo apt install apache2 php-fpm mysql-server

MSG
POSTINST
chmod 755 "$PKG_DIR/DEBIAN/postinst"

# DEBIAN/postrm
cat > "$PKG_DIR/DEBIAN/postrm" << 'POSTRM'
#!/bin/bash
set -e
if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then
    rm -rf /usr/lib/lamp-manager
    if command -v update-desktop-database > /dev/null; then
        update-desktop-database /usr/share/applications
    fi
    if command -v gtk-update-icon-cache > /dev/null; then
        gtk-update-icon-cache -f /usr/share/icons/hicolor
    fi
fi
POSTRM
chmod 755 "$PKG_DIR/DEBIAN/postrm"

# Construir el paquete
OUTPUT="$OUTPUT_DIR/${PKG_NAME}_${VERSION}_${ARCH}.deb"
dpkg-deb --root-owner-group --build "$PKG_DIR" "$OUTPUT"
rm -rf "$BUILD_DIR"

echo "✓ Paquete generado: $OUTPUT"
echo "  Instalar con: sudo dpkg -i $OUTPUT"
