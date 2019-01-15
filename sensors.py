import csv
import json
import math as m
import random
from datetime import timedelta
from os import path

import common


class MyCsv:
    """Classe base per caricare i dati dai csv nel formato utile allo script."""

    def __init__(self, name, csv_delimiter, csv_directory, time_offset: timedelta, logger: common.Logger,
                 auto_load=True):
        self.name = name
        self.delimiter = csv_delimiter
        self.directory = csv_directory
        self.time_offset = time_offset
        self.logger = logger
        self.contents = []
        if auto_load:
            self.load()

    def load(self):
        """Carica il file csv."""
        result = []
        file_path = path.join(self.directory, self.name + ".csv")
        try:
            with open(file_path, mode='r') as csv_file:
                reader = csv.reader(csv_file, delimiter=self.delimiter)
                for row in reader:
                    output_row = []
                    for col in row:
                        try:
                            # conversione delle stringhe numeriche in numeri (float se hanno la virgola, int altrimenti)
                            if "," in col:
                                number = float(col.replace(",", "."))
                            else:
                                number = int(col)
                            output_row.append(number)
                        except ValueError:
                            output_row.append(col)
                    result.append(output_row)
            self.contents = result
        except IOError:
            self.logger.log("Errore nell'apertura del file %s" % file_path, "error")

    def get_today_entry(self):
        """Restituisce l'entry del csv relativa ad oggi."""
        today = common.now(self.time_offset)
        return self.contents[today.day][today.month]


class ExtTempData(common.SensorData):
    """Rappresenta il generatore di temperature esterne tramite file csv e formula matematica."""

    def __init__(self, min_csv_name, max_csv_name, min_temp_hour: float, max_temp_hour: float,
                 csv_delimiter, csv_directory, time_offset: timedelta, logger: common.Logger):
        self.min_csv = MyCsv(min_csv_name, csv_delimiter, csv_directory, time_offset, logger)
        self.max_csv = MyCsv(max_csv_name, csv_delimiter, csv_directory, time_offset, logger)
        self.min_hour = min_temp_hour
        self.max_hour = max_temp_hour
        self.time_offset = time_offset
        self.__random_factor = random.random() / 15.0

    def query(self):
        """Restituisce la temperatura attuale interpolando minima e massima tramite una formula matematica."""
        now = common.now(self.time_offset)
        min_h = self.min_hour
        max_h = self.max_hour
        min_t = self.min_csv.get_today_entry()
        max_t = self.max_csv.get_today_entry()
        delta = int((now - now.replace(hour=0, minute=0, second=0, microsecond=0)).total_seconds() / 60)
        if delta < min_h:
            temp = max_t - (max_t - min_t) * m.exp(1) / (m.exp(1) - 1) * (
                    1 - m.exp(-((delta + (1440 - max_h)) ** 1.5) / ((min_h + (1440 - max_h)) ** 1.5)))
        elif delta < max_h:
            temp = min_t + (max_t - min_t) * m.exp(1) / (m.exp(1) - 1) * (
                    1 - m.exp(-(delta - min_h) / (max_h - min_h)))
        else:
            temp = max_t - (max_t - min_t) * m.exp(1) / (m.exp(1) - 1) * (
                    1 - m.exp(-((delta - max_h) ** 1.5) / ((min_h + (1440 - max_h)) ** 1.5)))
        temp = temp + (max_t - min_t) * self.__random_factor
        return round(temp, 2)


class CsvData(common.SensorData):
    """Rappresenta il generatore di dati di un sensore tramite file csv."""

    def __init__(self, name, frequency_minutes: int, variation_percent: float, csv_delimiter, csv_directory,
                 time_offset: timedelta, logger: common.Logger, cumulative=True, auto_gen=True):
        self.csv = MyCsv(name, csv_delimiter, csv_directory, time_offset, logger)
        self.frequency = frequency_minutes
        self.variation = variation_percent
        self.time_offset = time_offset
        self.cumulative = cumulative
        self.chunks = []
        self.date = None
        if auto_gen:
            self.generate()

    def generate(self):
        """Genera letture simulate da un sensore in base al csv."""
        date = common.now(self.time_offset).date()
        if self.date == date:
            # Se siamo sempre nello stesso giorno dell'ultima generazione, evito di rifarla
            return
        else:
            self.date = date
        result = []
        partial = 0.0
        variation = self.variation / 100.0
        total_chunks = 1440 // self.frequency
        number = self.csv.get_today_entry()
        for i in range(0, total_chunks):
            remainder = number - partial
            if remainder > 0.0:
                if i < total_chunks - 1:
                    remaining_chunks = total_chunks - i
                    # calcolo il chunk dell'esatta divisione in total_chunks parti
                    exact_chunk = remainder / remaining_chunks
                    # applico la variazione di +/- variation%
                    chunk = random.uniform(exact_chunk - exact_chunk * variation, exact_chunk + exact_chunk * variation)
                    # aggiungo il chunk così generato al totale parziale
                    partial += chunk
                    if self.cumulative:
                        result.append(partial)
                    else:
                        result.append(chunk)
                else:
                    # ultima iterazione: mi assicuro che il totale sia il numero preso dal csv
                    if self.cumulative:
                        result.append(number)
                    else:
                        result.append(remainder)
            else:
                # se la rimanenza è 0 non faccio alcun calcolo ulteriore
                if self.cumulative:
                    result.append(partial)
                else:
                    result.append(0.0)
        self.chunks = result

    def query(self):
        """Restituisce la lettura simulata relativa al tempo attuale."""
        now = common.now(self.time_offset)
        self.generate()
        delta = (now - now.replace(hour=0, minute=0, second=0, microsecond=0)).total_seconds()
        index = int(delta / (self.frequency * 60))
        return self.chunks[index]


class Sensor(common.IoTElement):
    """Rappresenta un sensore."""

    def __init__(self, config, client: common.Client, time_offset: timedelta,
                 s_id, data: common.SensorData, good_range, publish_interval: int, logger: common.Logger):
        super().__init__(config, client, time_offset, logger)

        self.gen_config = config.get("general")
        self.topics_config = config.get("topics")
        self.csv_config = config.get("csv")
        self.sensors_config = config.get("sensors")
        self.topic_root = self.topics_config.get("root")
        self.readings_topic = self.topic_root + "/%s/" + self.topics_config.get("readings")
        self.commands_topic = self.topic_root + "/%s/" + self.topics_config.get("commands")
        self.messages_topic = self.topic_root + "/%s/" + self.topics_config.get("messages")
        self.alarms_topic = self.topic_root + "/%s/" + self.topics_config.get("alarms")

        self.id = s_id
        self.data = data
        self.publish_interval = publish_interval
        self.good_range = good_range
        self.alarm_status = common.OnOffStatus.ON
        self.last_reading = None

    def publish_reading(self, reading):
        """Fa publish della lettura del sensore."""
        topic = self.readings_topic % self.id
        payload_obj = {
            "type": "reading",
            "argument": reading
        }
        payload = json.dumps(payload_obj)
        self.client.publish(topic, payload)

    def publish_alarm(self, argument):
        """Fa publish del messaggio di allarme del sensore."""
        topic = self.alarms_topic % self.id
        payload_obj = {
            "type": "danger",
            "time": common.now(self.time_offset).strftime("%F %T"),
            "argument": argument
        }
        payload = json.dumps(payload_obj)
        self.client.publish(topic, payload, 2)

    def subscribe_to_commands(self):
        """Fa subscribe ai comandi che possono essere inviati dal controller."""
        topic = self.commands_topic % self.id
        self.client.subscribe(topic, (lambda cl, us, message: self.commanded_action(message.payload)))

    def publish_feedback(self, argument):
        """Fa publish del messaggio di feedback sull'azione intrapresa dal sensore."""
        topic = self.messages_topic % self.id
        payload_obj = {
            "type": "ack",
            "argument": argument
        }
        payload = json.dumps(payload_obj)
        self.client.publish(topic, payload)

    def commanded_action(self, payload):
        """Esegue il comando contenuto nel payload specificato."""
        try:
            payload_obj = json.loads(payload)
        except ValueError:
            self.logger.log("Parsing di stringa JSON fallito:\n%s" % payload, "error")
        else:
            if payload_obj.get("command"):
                if payload_obj.get("command").lower() == "alarm_status":
                    self.alarm_status = common.OnOffStatus(payload_obj.get("argument"))
                self.publish_feedback(payload_obj)

    def loop(self):
        """L'iterazione eseguita dal thread."""
        self.subscribe_to_commands()
        while not self.thread.stopped:
            reading = self.data.query()
            self.publish_reading(reading)
            if self.alarm_status == common.OnOffStatus.ON and self.good_range and \
                    not common.in_good_range(reading, self.good_range) and reading != self.last_reading:
                self.publish_alarm(reading)
            self.last_reading = reading
            self.thread.wait(self.publish_interval)
