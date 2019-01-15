import json
import random
from datetime import timedelta

import common
import sensors


class Conditioner(common.IoTElement):
    """Rappresenta un condizionatore."""

    def __init__(self, config, client: common.Client, time_offset: timedelta, c_id, ext_temp_data: sensors.ExtTempData,
                 logger: common.Logger):
        super().__init__(config, client, time_offset, logger)

        self.gen_config = self.config.get("general")
        self.topics_config = self.config.get("topics")
        self.conditioners_config = self.config.get("conditioners")
        self.topic_root = self.topics_config.get("root")
        self.readings_topic = self.topic_root + "/%s/" + self.topics_config.get("readings")
        self.commands_topic = self.topic_root + "/%s/" + self.topics_config.get("commands")
        self.messages_topic = self.topic_root + "/%s/" + self.topics_config.get("messages")
        self.alarms_topic = self.topic_root + "/%s/" + self.topics_config.get("alarms")

        self.id = c_id
        self.publish_interval = self.conditioners_config.get("publish_interval")
        self.range = self.gen_config.get("good_range")
        self.status = common.OnOffStatus.ON
        self.alarm_status = common.OnOffStatus.ON
        self.current_temperature = self.target_temperature = self.previous_temperature = \
            self.gen_config.get("target_temperature", 20.0)
        self.variation_off = self.gen_config.get("variation_off", [0.02, 0.04])
        self.variation_on = self.gen_config.get("variation_on", [0.04, 0.08])
        self.ext_temp_data = ext_temp_data

    def publish_reading(self, reading):
        """Fa publish della lettura del condizionatore."""
        topic = self.readings_topic % self.id
        payload_obj = {
            "type": "reading",
            "argument": reading
        }
        payload = json.dumps(payload_obj)
        self.client.publish(topic, payload)

    def publish_alarm(self, argument):
        """Fa publish del messaggio di allarme del condizionatore."""
        topic = self.alarms_topic % self.id
        payload_obj = {
            "type": "temperature",
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
        """Fa publish del messaggio di feedback sull'azione intrapresa dal condizionatore."""
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
                if payload_obj.get("command").lower() == "status":
                    self.status = common.OnOffStatus(payload_obj.get("argument"))
                elif payload_obj.get("command").lower() == "alarm_status":
                    self.alarm_status = common.OnOffStatus(payload_obj.get("argument"))
                elif payload_obj.get("command").lower() == "target":
                    self.target_temperature = float(payload_obj.get("argument"))
                self.publish_feedback(payload_obj)

    def temperature_query(self):
        """Genera una lettura di temperatura tramite una formula inventata.
        Se si hanno dati di temperatura esterna, a condizionatore spento si muoverà verso di essa."""
        result = self.previous_temperature
        if self.ext_temp_data:
            ext_temp = self.ext_temp_data.query()
        else:
            # Senza temperatura esterna, si ottiene una lieve variazione dalla temperatura precedente
            ext_temp = result * random.uniform(-1.1, 1.1)
        if self.status == common.OnOffStatus.OFF:
            variation = (ext_temp - result) * random.uniform(self.variation_off[0], self.variation_off[1])
        else:
            variation = (self.target_temperature - result) * random.uniform(self.variation_on[0], self.variation_on[1])
        result += variation
        return round(result, 2)

    def loop(self):
        """L'iterazione eseguita dal thread."""
        self.subscribe_to_commands()
        while not self.thread.stopped:
            self.current_temperature = self.temperature_query()
            self.publish_reading(self.current_temperature)
            if self.current_temperature != self.previous_temperature:
                if self.alarm_status == common.OnOffStatus.ON and self.range and \
                        not common.in_good_range(self.current_temperature, self.range):
                    self.publish_alarm(self.current_temperature)
                self.previous_temperature = self.current_temperature
            self.thread.wait(self.publish_interval)
