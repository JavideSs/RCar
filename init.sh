#!/bin/bash

#Error handle
set -e
error_handler(){
    echo ""
    echo "ERROR: Command failed"
    exit 1
}
trap error_handler ERR

#Root
if [ "$(id -u)" -ne 0 ] && ! sudo --validate; then
    echo "Run as root: sudo $0"
    exit 1
fi

#Wifi
nmcli device wifi connect "WIFI NAME" password "WIFI PASSWORD"
nmcli con mod "WIFI NAME" ipv4.addresses <RASPBERRY IP>/24 ipv4.gateway <GATEWAY IP> ipv4.method manual
nmcli con up "WIFI NAME"

#Bluetooth
rfkill unblock all
systemctl restart bluetooth
hciconfig hci0 up

#Vnc
raspi-config nonint do_vnc 1
systemctl enable --now vncserver-x11-serviced

#Other
raspi-config nonint do_camera 1
raspi-config nonint do_ssh 1
raspi-config nonint do_spi 1
raspi-config nonint do_i2c 1
raspi-config nonint do_serial_cons 1
raspi-config nonint do_serial_hw 0
raspi-config nonint do_onewire 1
raspi-config nonint do_boot_behaviour B4

#Install dependencies
apt install python3-cwiid python3-evdev -y

#Apply changes
sudo apt update
echo "Configuration completed successfully."
sleep 5
reboot