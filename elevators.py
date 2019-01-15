import datetime
import json
import random
from enum import Enum

import common


class Direction(Enum):
    """Rappresenta la direzione dell'ascensore."""
    DOWN = -1
    STOP = 0
    UP = 1


class EStatus(Enum):
    """Rappresenta lo stato di funzionamento dell'ascensore."""
    OK = 0
    ERROR = 1
    MAINTENANCE = 2
    RESET = 3


class Elevator(common.IoTElement):
    """Rappresenta un ascensore."""

    def __init__(self, config, client: common.Client, time_offset: datetime.timedelta,
                 e_id, logger: common.Logger):
        super().__init__(config, client, time_offset, logger)

        self.gen_config = config.get("general")
        self.topics_config = config.get("topics")
        self.elevator_config = config.get("elevators")
        self.simulator_config = config.get("simulator")
        self.topic_root = self.topics_config.get("root")
        self.stats_topic = self.topic_root + "/%s/" + self.topics_config.get("stats")
        self.messages_topic = self.topic_root + "/%s/" + self.topics_config.get("messages")
        self.commands_topic = self.topic_root + "/%s/" + self.topics_config.get("commands")
        self.alarms_topic = self.topic_root + "/%s/" + self.topics_config.get("alarms")

        self.id = e_id
        self.failure_chance = self.elevator_config.get("failure_chance")
        self.publish_interval = self.elevator_config.get("publish_interval")
        self.served_floors = self.gen_config.get("floors")
        self.current_floor = random.choice(self.served_floors)
        self.destination_floor = self.current_floor
        self.stop_times = []
        for stop_time in self.gen_config.get("stop_times"):
            self.stop_times.append(common.TimeRange(stop_time[0], stop_time[1]))
        self.direction = Direction.STOP
        self.status = EStatus.OK

    def unavailable(self):
        """Restituisce true se l'ascensore è in uno stato non disponibile."""
        for stop_time in self.stop_times:
            if stop_time.now_in_range(self.time_offset):
                return True
        if not self.status == EStatus.OK:
            return True
        return False

    def get_stats(self):
        """Restituisce una stringa JSON che rappresenta le statistiche dell'ascensore."""
        payload_obj = {
            "floor": self.current_floor,
            "direction": self.direction.value
        }
        return json.dumps(payload_obj)

    def publish_stats(self):
        """Fa publish delle statistiche dell'ascensore."""
        topic = self.stats_topic % self.id
        payload = self.get_stats()
        self.client.publish(topic, payload)

    def publish_status(self):
        """Fa publish del messaggio di stato dell'ascensore."""
        topic = self.messages_topic % self.id
        payload_obj = {
            "type": "status",
            "argument": self.status.value
        }
        payload = json.dumps(payload_obj)
        self.client.publish(topic, payload)

    def subscribe_to_commands(self):
        """Fa subscribe ai comandi che possono essere inviati dal controller."""
        topic = self.commands_topic % self.id
        self.client.subscribe(topic, (lambda cl, us, message: self.commanded_action(message.payload)))

    def publish_feedback(self, argument):
        """Fa publish del messaggio di feedback sull'azione intrapresa dall'ascensore."""
        topic = self.messages_topic % self.id
        payload_obj = {
            "type": "ack",
            "argument": argument
        }
        payload = json.dumps(payload_obj)
        self.client.publish(topic, payload)

    def commanded_action(self, payload: str):
        """Esegue il comando contenuto nel payload specificato."""
        try:
            payload_obj = json.loads(payload)
        except ValueError:
            self.logger.log("Parsing di stringa JSON fallito:\n%s" % payload, "error")
        else:
            if payload_obj.get("command"):
                if payload_obj.get("command").lower() == "status":
                    self.status = EStatus(payload_obj.get("argument"))
                elif payload_obj.get("command").lower() == "floor_target":
                    self.destination_floor = int(payload_obj.get("argument"))
                self.publish_feedback(payload_obj)

    def spontaneous_actions(self):
        """Esegue le azioni spontanee dell'ascensore."""
        # Probabilità di guasto
        if random.random() < self.failure_chance:
            self.logger.log("L'ascensore si è guastato!")
            self.status = EStatus.ERROR
        # Gestione status
        if self.destination_floor not in self.served_floors:
            # se il piano di destinazione non esiste, mando automaticamente l'ascensore in reset
            self.status = EStatus.RESET
        if self.status == EStatus.RESET:
            # Reset dell'ascensore: va al piano terra e dopo si mette in stato di manutenzione
            if self.current_floor != 0:
                self.destination_floor = 0
            else:
                self.status = EStatus.MAINTENANCE
        elif self.status != EStatus.OK:
            return
        # Gestione movimento
        self.current_floor += self.direction.value
        if self.destination_floor < self.current_floor:
            self.direction = Direction.DOWN
        elif self.destination_floor > self.current_floor:
            self.direction = Direction.UP
        else:
            self.direction = Direction.STOP

    def loop(self):
        """L'iterazione eseguita dal thread."""
        self.subscribe_to_commands()
        prev_status = None
        while not self.thread.stopped:
            if self.status != prev_status:
                self.publish_status()
                prev_status = self.status
            self.spontaneous_actions()
            self.publish_stats()
            self.thread.wait(self.publish_interval)


class InputSimulator(common.IoTElement):
    """Rappresenta utenti che interagiscono con l'ascensore."""

    def __init__(self, config, time_offset: datetime.timedelta, elevator: Elevator, logger: common.Logger):
        super().__init__(config, None, time_offset, logger)

        self.gen_config = config.get("general")
        self.simulator_config = config.get("simulator")

        self.elevator = elevator
        self.normal_interval = self.simulator_config.get("normal_interval")
        self.busy_interval = self.simulator_config.get("busy_interval")
        self.busy_times = []

        for busy_time in self.gen_config.get("busy_times"):
            self.busy_times.append(common.TimeRange(busy_time[0], busy_time[1]))

    def interact(self):
        """Simula un'interazione con l'ascensore."""
        if self.elevator.unavailable():
            self.logger.log("Tentata interazione con l'ascensore %s, ma non era disponibile." % self.elevator.id)
            return
        other_floors = list(self.elevator.served_floors)
        other_floors.remove(self.elevator.current_floor)
        user_floor = random.choice(other_floors)
        msg_start = "Utente al piano %s chiama l'ascensore %s..." % (user_floor, self.elevator.id)
        if self.elevator.direction != Direction.STOP:
            self.logger.log("%s ma l'ascensore è in movimento e non riceve il comando." % msg_start)
        else:
            self.logger.log("%s e l'ascensore accetta il comando." % msg_start)
            self.elevator.destination_floor = user_floor

    def loop(self):
        while not self.thread.stopped:
            interval = self.normal_interval
            for busy_time in self.busy_times:
                if busy_time.now_in_range(self.time_offset):
                    interval = self.busy_interval
                    break
            self.interact()
            self.thread.wait(interval)
