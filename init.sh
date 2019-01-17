git clone -b files-15012019 https://github.com/andreapiccaluga/tesi-iot .
rm -rf node-red
if [ $HOSTNAME -ne "alarm-vm" ]; then
	rm alarms.json
fi
if [ $HOSTNAME -ne "climate-vm" ]; then
	rm conditioners.json
fi
if [ $HOSTNAME -ne "cryo-vm" ]; then
	rm -rf csv
	rm sensors.json
fi
if [ $HOSTNAME -ne "elev-vm" ]; then
	rm sensors.json
fi
