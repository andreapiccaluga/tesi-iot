cd /root
read -p "Riclonare da git (s/N)? " SCELTA1
case "$SCELTA1" in
	s|S )
		if [ -z "$(apk -e info git)" ]; then
			apk add git
		fi
		rm -rf app
		git clone -b files-15012019 https://github.com/andreapiccaluga/tesi-iot ./app
	;;
esac
cd /root/app
rm -rf node-red
echo "Cancellazione dei file non pertinenti a $HOSTNAME."
if [ "$HOSTNAME" != "alarm-vm" ]; then
	rm alarms.json
fi
if [ "$HOSTNAME" != "climate-vm" ]; then
	rm conditioners.json
fi
if [ "$HOSTNAME" != "cryo-vm" ]; then
	rm -rf csv
	rm sensors.json
fi
if [ "$HOSTNAME" != "elev-vm" ]; then
	rm elevators.json
fi
read -p "Installare script di boot (s/N)? " SCELTA2
case "$SCELTA2" in
	s|S ) mv boot_script.sh /etc/profile.d/
esac
mv init.sh /root/
cd /root
