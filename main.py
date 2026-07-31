import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.logger import setup_logging
from app.instance_manager import InstanceManager
from app.main_window import MainWindow


setup_logging()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)


def start_gui():
    app = MainWindow()
    app.run()


if __name__ == "__main__":
    manager = InstanceManager()
    manager.run(start_gui)
