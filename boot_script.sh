cd /root

COMMAND="python3 runner.py"

until $COMMAND; do
	echo Riavvio dello script in corso.
	sleep 1
done
