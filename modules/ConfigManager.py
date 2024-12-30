import yaml
import logging.config
from pathlib import Path

log = logging.getLogger(__name__)

class libmbus2mqtt:
    '''libmbus2mqtt program configuration class'''
    def __init__(self, file: Path):
        self.FLAG_ERROR = False

        self.file = file
        self.load()

    def load(self):
        log.debug(f"Loading libmbus2mqtt config from {self.file}...")
        with open(self.file) as file:
            try:
                cfg = yaml.safe_load(file)
                log.debug(f"Successfuly loaded config.")
            except FileNotFoundError:
                log.error(f"Cannot load {self.file}: File not found.")
                self.FLAG_ERROR = True
                return
            except Exception as e:
                log.exception(e)
                self.FLAG_ERROR = True
                return
        
        for section in cfg:
            self.__dict__[section] = cfg[section]