#!/usr/bin/bash
# Build the DarkSky icon theme

if [ $UID -ne 0 ]; then
    printf "[!] Only root can do this!\n"
    exit 1
fi

if ! [ -d "/usr/share/icons/korla" ]; then
    echo '"/usr/share/icons/korla" does not exist!'
    exit 1
fi
if ! [ -d "/usr/share/icons/Flatery-Dark" ]; then
    echo '"/usr/share/icons/Flatery-Dark" does not exist!'
    exit 1
fi
if ! [ -d "/usr/share/icons/vimix-cursors" ]; then
    echo '"/usr/share/icons/vimix-cursors" does not exist!'
    exit 1
fi

THEME_DIR="/usr/share/icons/DarkSky"
if [ -e "$THEME_DIR" ]; then
    rm -rf "$THEME_DIR"
fi

cp -R "/usr/share/icons/Flatery-Dark" "$THEME_DIR"
if [ $? -ne 0 ]; then
    exit 0
fi

rm -rf "${THEME_DIR}/apps" 2> /dev/null
rm -f "${THEME_DIR}/index.theme" 2> /dev/null
rm -f "${THEME_DIR}/icon-theme.cache" 2> /dev/null
find "${THEME_DIR}/actions" -type l -name go-* -delete 2> /dev/null
find "${THEME_DIR}/actions" -type f -name go-* -delete 2> /dev/null

ln -s "/usr/share/icons/korla/apps" "${THEME_DIR}/apps" 2> /dev/null
ln -s "/usr/share/icons/vimix-cursors/cursors" "${THEME_DIR}/cursors" 2> /dev/null
ln -s "/usr/share/themes/DarkSky/icons.theme" "${THEME_DIR}/index.theme" 2> /dev/null

for icon in $(find "/usr/share/icons/korla/actions" -type f -name go-* -ls | awk '{print $11}'); do
    for d in $(ls "${THEME_DIR}/actions"); do
        if [ -d "${THEME_DIR}/actions/${d}" ]; then
            ln -s "$icon" "${THEME_DIR}/actions/${d}/" 2> /dev/null
        fi
    done
done

chown root:root -R "$THEME_DIR"
find "$THEME_DIR" -type d -exec chmod 0755 {} \;
find "$THEME_DIR" -type f -exec chmod 0644 {} \;
exit 0
