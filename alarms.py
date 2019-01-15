import json
from datetime import timedelta
from enum import Enum
import random

import common


class AlarmType(Enum):
    PERIMETER = 1
    VOLUMETRIC = 2


class Alarm(common.IoTElement):
    """Rappresenta un allarme anti-intrusione."""

    def __init__(self, config, client: common.Client, time_offset: timedelta, a_id, logger: common.Logger):
        super().__init__(config, client, time_offset, logger)

        self.topics_config = self.config.get("topics")
        self.alarms_config = self.config.get("alarms")
        self.topic_root = self.topics_config.get("root")
        self.commands_topic = self.topic_root + "/%s/" + self.topics_config.get("commands")
        self.messages_topic = self.topic_root + "/%s/" + self.topics_config.get("messages")
        self.alarms_topic = self.topic_root + "/%s/" + self.topics_config.get("alarms")

        self.id = a_id
        if "V" in self.id:
            self.type = AlarmType.VOLUMETRIC
        else:
            self.type = AlarmType.PERIMETER
        self.check_interval = self.alarms_config.get("check_interval")
        if self.type == AlarmType.VOLUMETRIC:
            self.trigger_chance = self.alarms_config.get("trigger_chance_volumetric")
        else:
            self.trigger_chance = self.alarms_config.get("trigger_chance_perimeter")
        self.alarm_status = common.OnOffStatus.ON

    def publish_alarm(self):
        """Fa publish del messaggio di allarme."""
        topic = self.alarms_topic % self.id
        payload_obj = {
            "type": "alarm",
            "time": common.now(self.time_offset).strftime("%F %T")
        }
        payload = json.dumps(payload_obj)
        self.client.publish(topic, payload, 2)

    def subscribe_to_commands(self):
        """Fa subscribe ai comandi che possono essere inviati dal controller."""
        topic = self.commands_topic % self.id
        self.client.subscribe(topic, (lambda cl, us, message: self.commanded_action(message.payload)))

    def publish_feedback(self, argument):
        """Fa publish del messaggio di feedback sull'azione intrapresa dall'allarme."""
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
            # Probabilità di scattare
            if random.random() < self.trigger_chance:
                if self.alarm_status == common.OnOffStatus.ON:
                    self.logger.log("Il sensore %s è scattato, e l'allarme è attivo!" % self.id)
                    self.publish_alarm()
                else:
                    self.logger.log("Il sensore %s è scattato, ma l'allarme era inattivo." % self.id)
            self.thread.wait(self.check_interval)
