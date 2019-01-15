import abc
import datetime
import json
import logging
import logging.handlers
import os
from enum import Enum
from threading import Thread, Event

import paho.mqtt.client as mqtt


class OnOffStatus(Enum):
    """Rappresenta uno stato che può essere on o off."""
    OFF = 0
    ON = 1


class Logger:
    """Permette di mantenere facilmente un log."""

    def __init__(self, name: str, console_level: int = logging.DEBUG, file_level: int = logging.DEBUG,
                 max_size_mb: int = 50, backup_count: int = 10):
        formatter = "%(asctime)s [%(levelname)s] %(message)s"
        logger = logging.getLogger(name)
        logger.setLevel(logging.DEBUG)
        ch = logging.StreamHandler()
        ch.setLevel(console_level)
        ch.setFormatter(logging.Formatter(formatter))
        logger.addHandler(ch)
        fh = logging.handlers.RotatingFileHandler("%s.log" % name, maxBytes=max_size_mb * 1048576,
                                                  backupCount=backup_count)
        fh.setLevel(file_level)
        fh.setFormatter(logging.Formatter(formatter))
        logger.addHandler(fh)
        self.name = name
        self.logger = logger

    def log(self, msg: str, level: str = "debug"):
        """Logga il messaggio specificato con il livello di importanza specificato tramite stringa."""
        try:
            il = getattr(logging, level.upper())
        except AttributeError:
            il = logging.DEBUG
        self.logger.log(il, msg)


def load_config(file_path: str, logger: Logger):
    """Carica il file di configurazione specificato, in formato json."""
    if os.path.exists(file_path):
        try:
            with open(file_path) as handle:
                config_obj_file = json.load(handle)
        except IOError:
            logger.log("Errore nel caricamento del file di configurazione %s." % file_path, "error")
            return None
        return config_obj_file
    else:
        logger.log("File di configurazione %s non trovato: non verranno creati thread di questo tipo." % file_path)
        return None


def now(offset: datetime.timedelta):
    """Restituisce l'orario attuale, eventualmente modificato dall'offset."""
    return datetime.datetime.now() + offset


def in_good_range(value: float, good_range: list):
    """Restituisce true se il valore è nel range specificato."""
    return good_range[0] <= value <= good_range[1]


def array_to_time(array: list):
    """Converte un array [h, m] nel formato datetime.time."""
    if array:
        h = array[0]
        m = array[1]
        return datetime.time(h, m)
    else:
        return datetime.time(0, 0)


def time_in_range(start, end, x):
    """Restituisce true se x è nel range [start, end]."""
    if start <= end:
        return start <= x <= end
    else:
        return start <= x or x <= end


class TimeRange:
    """Rappresenta un range temporale."""

    def __init__(self, start, end):
        if isinstance(start, list):
            self.start = array_to_time(start)
        else:
            self.start = start
        if isinstance(end, list):
            self.end = array_to_time(end)
        else:
            self.end = end

    def now_in_range(self, time_offset):
        """Restituisce true se l'orario attuale è nel range."""
        return time_in_range(self.start, self.end, now(time_offset).time())


class Client:
    """Wrapper per il client MQTT."""

    def __init__(self, host, port: int, username, password, last_will_topic,
                 last_will_payload_obj, logger: Logger):
        self.online = True
        self.host = host
        self.port = port
        self.mqtt = mqtt.Client()
        self.logger = logger
        if username:
            self.username = username
            self.password = password
            self.mqtt.username_pw_set(self.username, self.password)
        if last_will_topic and last_will_payload_obj:
            self.mqtt.will_set(last_will_topic, json.dumps(last_will_payload_obj))
        try:
            self.mqtt.connect(self.host, self.port)
            self.mqtt.loop_start()
        except:
            self.logger.log("Impossibile connettersi al broker %s:%s. Modalità offline attivata." % (host, port),
                            "error")
            self.online = False
        if self.online:
            self.logger.log("Connesso al broker %s:%s." % (host, port))

    def publish(self, topic, payload, qos=0, retain=False):
        """Fa publish sul topic specificato."""
        if self.online:
            self.mqtt.publish(topic, payload, qos, retain)
        self.logger.log("%s : %s" % (topic, payload))

    def subscribe(self, topic, callback, qos=0):
        """Fa subscribe al topic specificato."""
        if self.online:
            self.mqtt.subscribe(topic, qos)
            self.mqtt.message_callback_add(topic, callback)
        self.logger.log("Subscribe: %s" % topic)

    def disconnect(self):
        """Disconnette il client dal broker."""
        if self.online:
            self.online = False
            self.mqtt.disconnect()

    def __del__(self):
        self.disconnect()


class SensorData(abc.ABC):
    """Interfaccia per i dati simulati dei sensori. Non istanziare."""

    @abc.abstractmethod
    def query(self):
        pass


class StoppableThread(Thread):
    """Thread che può essere fermato tramite chiamata a funzione stop, ammesso che si usi wait al posto di sleep."""

    def __init__(self, target):
        super().__init__(target=target)
        self.__event = Event()
        self.stopped = False

    def stop(self):
        self.__event.set()

    def wait(self, interval):
        self.stopped = self.__event.wait(interval)


class IoTElement:
    """Classe base per i simulatori di dispositivi IoT. Inizializza le impostazioni comuni."""

    def __init__(self, config_obj, client: Client, time_offset: datetime.timedelta, logger: Logger):
        self.config = config_obj
        self.client = client
        self.thread = None
        self.time_offset = time_offset
        self.logger = logger

    def init_thread(self, target):
        """Inizializza il thread e lo ritorna per poterlo fermare in seguito."""
        self.thread = StoppableThread(target)
        return self.thread
