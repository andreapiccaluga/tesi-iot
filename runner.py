#!/usr/bin/python3

import datetime
import time

import alarms
import common
import conditioners
import elevators
import sensors


def main():
    logger = common.Logger("scripts")
    logger.log("*** Partenza degli script ***")

    runner_config = common.load_config("runner.json", logger)
    gen_config = runner_config.get("general")
    ids_config = runner_config.get("ids")
    client_config = runner_config.get("client")

    time_offset = datetime.timedelta(hours=gen_config.get("time_offset_hours", 0.0))
    host = client_config.get("host", "localhost")
    port = client_config.get("port", 1883)
    uname = client_config.get("username")
    pword = client_config.get("password")
    lwp = client_config.get("last_will_payload")

    clients = []
    threads = []

    sys_cl = common.Client(host, port, uname, pword, None, None, logger)
    clients.append(sys_cl)
    # Il seguente messaggio segnala l'inizio degli script. Lato Node-RED mette tutti gli switch sui valori di default.
    sys_cl.publish("system", "wake")

    # Ascensori
    config = common.load_config("elevators.json", logger)
    if config:
        ids = ids_config.get("elevators")
        topics = config.get("topics")
        alarms_topic = topics.get("root") + "/%s/" + topics.get("alarms")
        for e_id in ids:
            cl = common.Client(host, port, uname, pword, alarms_topic % e_id, lwp, logger)
            clients.append(cl)
            el = elevators.Elevator(config, cl, time_offset, e_id, logger)
            sim = elevators.InputSimulator(config, time_offset, el, logger)
            threads.append(el.init_thread(el.loop))
            threads.append(sim.init_thread(sim.loop))

    # Sensori
    config = common.load_config("sensors.json", logger)
    if config:
        gen = config.get("general")
        topics = config.get("topics")
        sensors_config = config.get("sensors")
        csv_config = config.get("csv")
        csv_delimiter = csv_config.get("delimiter", ";")
        csv_directory = csv_config.get("directory", ".")
        ids = csv_config.get("other_sensors", [])
        ranges = csv_config.get("good_ranges", [])
        alarms_topic = topics.get("root") + "/%s/" + topics.get("alarms")
        xtemp_sensor_id = "ExternalTemperature"

        ext_temp_data = sensors.ExtTempData(
            csv_config.get("min_temperature", "Minima"),
            csv_config.get("max_temperature", "Massima"),
            gen.get("min_hour", 7.0),
            gen.get("max_hour", 14.0),
            csv_delimiter, csv_directory, time_offset, logger)

        cl = common.Client(host, port, uname, pword, alarms_topic % xtemp_sensor_id, lwp, logger)
        clients.append(cl)
        se = sensors.Sensor(config, cl, time_offset, xtemp_sensor_id, ext_temp_data, None,
                            sensors_config.get("publish_interval_temperature", 60), logger)
        threads.append(se.init_thread(se.loop))
        for i in range(len(ids)):
            s_id = ids[i]
            good_range = ranges[i]
            cl = common.Client(host, port, uname, pword, alarms_topic % s_id, lwp, logger)
            clients.append(cl)
            se = sensors.Sensor(config, cl, time_offset, s_id,
                                sensors.CsvData(
                                    s_id, 30, 30.0, csv_delimiter, csv_directory, time_offset, logger
                                ), good_range, sensors_config.get("publish_interval_other", 1800), logger)
            threads.append(se.init_thread(se.loop))

    # Condizionatori
    config = common.load_config("conditioners.json", logger)
    if config:
        ids = ids_config.get("conditioners")
        for c_id in ids:
            cl = common.Client(host, port, uname, pword, alarms_topic % c_id, lwp, logger)
            clients.append(cl)
            ac = conditioners.Conditioner(config, cl, time_offset, c_id, ext_temp_data, logger)
            threads.append(ac.init_thread(ac.loop))

    # Allarmi
    config = common.load_config("alarms.json", logger)
    if config:
        ids = ids_config.get("alarms")
        for a_id in ids:
            cl = common.Client(host, port, uname, pword, alarms_topic % a_id, lwp, logger)
            clients.append(cl)
            al = alarms.Alarm(config, cl, time_offset, a_id, logger)
            threads.append(al.init_thread(al.loop))

    for t in threads:
        t.start()

    while True:
        try:
            time.sleep(100000)
        except KeyboardInterrupt:
            logger.log("*** CTRL+C rilevato ***")
            for t in threads:
                t.stop()
                t.join()
            # Il seguente messaggio segnala l'interruzione degli script. Verrà registrato nel log della dashboard.
            # ATTENZIONE: Disabilitato per il caso con più macchine diverse in quanto perde di significato.
            # sys_cl.publish("system", "sleep")
            for c in clients:
                c.disconnect()
            exit(0)
            break


if __name__ == "__main__":
    main()
