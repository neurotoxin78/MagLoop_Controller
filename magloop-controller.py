import gc
import json as jconf
import sys
from pathlib import Path
from time import sleep

import requests
from PyQt6 import QtCore
from PyQt6 import QtWidgets
from PyQt6.QtCore import QFile
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QStandardItemModel
from PyQt6.uic import loadUi
from pympler import muppy
from pympler import summary
from rich.console import Console

con = Console()


def extended_exception_hook(exec_type, value, traceback):
    # Print the error and traceback
    con.log(exec_type, value, traceback)
    # Call the normal Exception hook after
    sys._excepthook(exec_type, value, traceback)
    sys.exit(1)


class AddDialog(QtWidgets.QDialog):
    def __init__(self):
        super().__init__()
        self.desclineEdit = None
        self.steplineEdit = None
        self.bandlineEdit = None
        self.relay1checkBox = None
        self.relay2checkBox = None
        self.relay3checkBox = None
        self.relay4checkBox = None
        # loadUi('add_dialog.ui', self)
        self.load_ui()
        self.setWindowTitle("Додати")
        self.setStylesheet("stylesheets/cap_control.qss")

    def load_ui(self):
        path = Path(__file__).resolve().parent / "ui/add_dialog.ui"
        ui_file = QFile(str(path))
        ui_file.open(QFile.OpenModeFlag.ReadOnly)
        loadUi(ui_file, self)
        ui_file.close()

    def set_fields_values(self, band: str, step: int, relay1: bool, relay2: bool, relay3: bool, relay4: bool,
                          desc: str):
        self.bandlineEdit.setText(band)
        self.steplineEdit.setText(step)
        self.desclineEdit.setText(desc)
        self.relay1checkBox.setChecked(bool(relay1))
        self.relay2checkBox.setChecked(bool(relay2))
        self.relay3checkBox.setChecked(bool(relay3))
        self.relay4checkBox.setChecked(bool(relay4))

    def get_fields_values(self):
        band = self.bandlineEdit.text()
        step = self.steplineEdit.text()
        desc = self.desclineEdit.text()
        relay1 = self.relay1checkBox.isChecked()
        relay2 = self.relay2checkBox.isChecked()
        relay3 = self.relay3checkBox.isChecked()
        relay4 = self.relay4checkBox.isChecked()
        return {
            "band": band, "step": step, "relay1": relay1, "relay2": relay2, "relay3": relay3, "relay4": relay4,
            "desc": desc
            }

    def setStylesheet(self, filename):
        with open(filename, "r") as fh:
            self.setStyleSheet(fh.read())


class MainWindow(QtWidgets.QMainWindow):
    BAND, STEPS, RELAY1, RELAY2, RELAY3, RELAY4, DESCRIPTION = range(7)

    def __init__(self, *args, **kwargs):
        super(MainWindow, self).__init__(*args, **kwargs)
        # Load the UI Page
        # loadUi('ui.ui', self)
        self.load_ui()
        self.status_label = QtWidgets.QLabel("Статус: ")
        self.relay1_status_label = QtWidgets.QLabel("1:OFF")
        self.relay2_status_label = QtWidgets.QLabel("2:OFF")
        self.relay3_status_label = QtWidgets.QLabel("3:OFF")
        self.relay4_status_label = QtWidgets.QLabel("4:OFF")
        self.statusbar.addPermanentWidget(self.status_label)
        self.statusbar.addPermanentWidget(self.relay1_status_label)
        self.statusbar.addPermanentWidget(self.relay2_status_label)
        self.statusbar.addPermanentWidget(self.relay3_status_label)
        self.statusbar.addPermanentWidget(self.relay4_status_label)
        self.statusbar.reformat()
        self.setStylesheet("stylesheets/cap_control.qss")
        self.add_dialog = AddDialog()
        # Main Timer
        self.main_Timer = QtCore.QTimer()
        self.main_Timer.timeout.connect(self.mainTimer)
        self.main_Timer.start(60000)
        # Variables
        self.connected: bool = False
        self.direction = None
        self.step: int = 0
        self.relay1: bool = False
        self.relay2: bool = False
        self.relay3: bool = False
        self.relay4: bool = False
        self.speed: int = 10
        self.current_position: int | str = 0
        self.max_position: int | str = 0
        self.api_status: str = ""
        self.api_park: str = ""
        self.api_move: str = ""
        self.api_relay: str = ""
        self.url: str = ""
        self.autoconect: bool = False
        self.current_treeIndex = 0
        self.all_objects = muppy.get_objects()
        self.initUI()
        self.configure()
        self.bandTreeViewConfig()
        self.load_bandTree()
        self.autoconnect()

    def load_ui(self):
        path = Path(__file__).resolve().parent / "ui/ui.ui"
        ui_file = QFile(str(path))
        ui_file.open(QFile.OpenModeFlag.ReadOnly)
        loadUi(ui_file, self)
        ui_file.close()

    def initUI(self):
        self.upButton.clicked.connect(self.upButton_click)
        self.downButton.clicked.connect(self.downButton_click)
        self.connectButton.clicked.connect(self.connectButton_click)
        self.parkButton.clicked.connect(self.parkButton_click)
        self.addButton.clicked.connect(self.addButton_click)
        self.bandtreeView.clicked.connect(self.getValue)
        self.runButton.clicked.connect(self.runButton_click)
        self.deleteButton.clicked.connect(self.deleteButton_click)
        self.autoConCheckBox.toggled.connect(self.set_autoconnect)
        self.relay1checkBox.toggled.connect(self.switch_relay_1)
        self.relay2checkBox.toggled.connect(self.switch_relay_2)
        self.relay3checkBox.toggled.connect(self.switch_relay_3)
        self.relay4checkBox.toggled.connect(self.switch_relay_4)
        self.comboInit()
        self.setButtons(False)
        con.log(F"UI Initialized")

    def setButtons(self, state: bool) -> None:
        self.upButton.setEnabled(state)
        self.downButton.setEnabled(state)
        self.parkButton.setEnabled(state)
        self.runButton.setEnabled(state)

    def switch_relay_1(self):
        self.set_relay("1", self.relay1checkBox.isChecked())
        self.relay1 = self.relay1checkBox.isChecked()

    def switch_relay_2(self):
        self.set_relay("2", self.relay2checkBox.isChecked())
        self.relay2 = self.relay2checkBox.isChecked()

    def switch_relay_3(self):
        self.set_relay("3", self.relay3checkBox.isChecked())
        self.relay3 = self.relay3checkBox.isChecked()

    def switch_relay_4(self):
        self.set_relay("4", self.relay4checkBox.isChecked())
        self.relay4 = self.relay4checkBox.isChecked()

    def set_relay(self, num: str, sw: bool):
        if self.connected:
            if sw:
                json = {'switch': "0", 'num': f'{str(num)}'}
                # self.relay = True
            else:
                json = {'switch': "1", 'num': f'{str(num)}'}
                # self.relay = False
            resp = requests.post(self.url + self.api_relay, json = json)
            json = resp.json()
            if 'status' in json:
                # stat = json["status"]
                match int(num):
                    case 1:
                        self.relay1_status_label.setText(F"1:{json['status']}")
                    case 2:
                        self.relay2_status_label.setText(F"2:{json['status']}")
                    case 3:
                        self.relay3_status_label.setText(F"3:{json['status']}")
                    case 4:
                        self.relay4_status_label.setText(F"4:{json['status']}")

    def autoconnect(self):
        self.autoconect = self.autoConCheckBox.isChecked()
        if self.autoconect:
            self.connectButton_click()

    def set_autoconnect(self):
        self.autoconect = self.autoConCheckBox.isChecked()
        con.log(F"Set autoconnect: {self.autoconect}")

    @staticmethod
    def connect(url):
        try:
            req = requests.get(url + "/settings")
            con.log(F"Connected")
            return req
        except ConnectionError:
            con.log("Network error")
            raise ConnectionError("Error connect to device. Check IP:PORT ")

    @staticmethod
    def get_json_config(filename: str):
        try:
            with open(filename, "r") as f:
                config = jconf.load(f)
            con.log(F"Load Config: {filename}")
            return config
        except FileNotFoundError:
            raise FileNotFoundError(F"File {filename} not found.")

    def load_bandTree(self):
        config = self.get_json_config("bands.json")
        if "bands" in config:
            bands = config["bands"]
            for key in bands:
                self.addTreeItem(
                    self.model, bands[key]['band'], bands[key]['step'], bands[key]['relay1'], bands[key]['relay2'],
                    bands[key]['relay3'], bands[key]['relay4'], bands[key]['desc']
                    )
        else:
            raise KeyError("Error: Key 'bands' not found in config file.")

    def store_bandTree(self):
        d_dict = {'bands': {}}
        for row in range(self.model.rowCount()):
            d_dict['bands'][row] = {}
            for column in range(self.model.columnCount()):
                index = self.model.index(row, column)
                match column:
                    case 0:
                        d_dict['bands'][row]['band'] = str(self.model.data(index))
                    case 1:
                        d_dict['bands'][row]['step'] = str(self.model.data(index))
                    case 2:
                        d_dict['bands'][row]['relay1'] = bool(self.model.data(index))
                    case 3:
                        d_dict['bands'][row]['relay2'] = bool(self.model.data(index))
                    case 4:
                        d_dict['bands'][row]['relay3'] = bool(self.model.data(index))
                    case 5:
                        d_dict['bands'][row]['relay4'] = bool(self.model.data(index))
                    case 6:
                        d_dict['bands'][row]['desc'] = str(self.model.data(index))
        with open("bands.json", "w") as fp:
            jconf.dump(d_dict, fp)

    def store_defaults(self):
        defaults = {
            "defaults": {
                "step": self.step, "speed": self.speed, "autoconnect": self.autoconect, "relay1": self.relay1,
                "relay2": self.relay2, "relay3": self.relay3, "relay4": self.relay4
                }
            }
        defaults = jconf.dumps(defaults, indent = 4)
        jsondefs = jconf.loads(defaults)
        try:
            with open("defaults.json", "w") as f:
                jconf.dump(jsondefs, f)
        except Exception:
            raise FileNotFoundError("File defaults.json not found.")

    def configure(self):
        config = self.get_json_config("api.json")
        if "api" in config:
            api = config["api"]
            self.url = api["url"]
            self.api_move = api["move"]
            self.api_park = api["park"]
            self.api_status = api["status"]
            self.api_relay = api["relay"]
            self.url_lineEdit.setText(self.url)
            con.log(F"Loaded API config")
        else:
            raise KeyError("Error: Key 'api' not found in config file.")
        defaults = self.get_json_config("defaults.json")
        if "defaults" in defaults:
            d = defaults["defaults"]
            self.step = d["step"]
            self.speed = d["speed"]
            self.relay1 = d["relay1"]
            self.relay2 = d["relay2"]
            self.relay3 = d["relay3"]
            self.relay4 = d["relay4"]
            step_index = self.step_comboBox.findText(self.step)
            self.step_comboBox.setCurrentIndex(step_index)
            speed_index = self.speed_comboBox.findText(self.speed)
            self.speed_comboBox.setCurrentIndex(speed_index)
            con.log(F"Autoconnect: {bool(d['autoconnect'])}")
            if bool(d['autoconnect']):
                self.autoConCheckBox.setChecked(True)
            if bool(d['relay1']):
                self.relay1checkBox.setChecked(True)
                self.relay1_status_label.setText(F"1: ON")
                self.switch_relay_1()
            if bool(d['relay2']):
                self.relay2checkBox.setChecked(True)
                self.relay2_status_label.setText(F"2: ON")
                self.switch_relay_2()
            if bool(d['relay3']):
                self.relay3checkBox.setChecked(True)
                self.relay3_status_label.setText(F"3: ON")
                self.switch_relay_3()
            if bool(d['relay4']):
                self.relay4checkBox.setChecked(True)
                self.relay4_status_label.setText(F"4: ON")
                self.switch_relay_4()
            con.log(F"Loaded defaults")
        else:
            raise KeyError("Error: Key 'defaults' not found in config file.")
        self.mainTimer()

    def bandTreeViewConfig(self):
        self.bandtreeView.setRootIsDecorated(False)
        self.bandtreeView.setAlternatingRowColors(True)
        self.model = self.createBandTreeModel(self)
        self.bandtreeView.setModel(self.model)
        self.bandtreeView.setSortingEnabled(True)
        self.bandtreeView.setColumnWidth(0, 160)
        self.bandtreeView.setColumnWidth(1, 60)
        self.bandtreeView.setColumnWidth(2, 40)
        self.bandtreeView.setColumnWidth(3, 40)
        self.bandtreeView.setColumnWidth(4, 40)
        self.bandtreeView.setColumnWidth(5, 40)
        self.bandtreeView.setColumnWidth(6, 160)

    def createBandTreeModel(self, parent):
        model = QStandardItemModel(0, 7, parent)
        model.setHeaderData(self.BAND, Qt.Orientation.Horizontal, "Діапазон")
        model.setHeaderData(self.STEPS, Qt.Orientation.Horizontal, "Кроки")
        model.setHeaderData(self.RELAY1, Qt.Orientation.Horizontal, "1")
        model.setHeaderData(self.RELAY2, Qt.Orientation.Horizontal, "2")
        model.setHeaderData(self.RELAY3, Qt.Orientation.Horizontal, "3")
        model.setHeaderData(self.RELAY4, Qt.Orientation.Horizontal, "4")
        model.setHeaderData(self.DESCRIPTION, Qt.Orientation.Horizontal, "Опис")
        return model

    def addTreeItem(self, model, band, steps, relay1, relay2, relay3, relay4, desc):
        model.insertRow(0)
        model.setData(model.index(0, self.BAND), band)
        model.setData(model.index(0, self.STEPS), steps)
        model.setData(model.index(0, self.RELAY1), relay1)
        model.setData(model.index(0, self.RELAY2), relay2)
        model.setData(model.index(0, self.RELAY3), relay3)
        model.setData(model.index(0, self.RELAY4), relay4)
        model.setData(model.index(0, self.DESCRIPTION), desc)
        con.log(
            F"Added items Band: {band}, Step : {steps}, Relay1 : {relay1}, Relay2 : {relay2}, Relay3 : {relay3}, "
            F"Relay4 : {relay4}, Description: {desc}"
            )

    def deleteButton_click(self):
        indices = self.bandtreeView.selectionModel().selectedRows()
        for index in sorted(indices):
            self.model.removeRow(index.row())

    def runButton_click(self):
        if self.connected:
            rows = {index.row() for index in self.bandtreeView.selectionModel().selectedIndexes()}
            output = []
            for row in rows:
                row_data = []
                for column in range(self.bandtreeView.model().columnCount()):
                    index = self.bandtreeView.model().index(row, column)
                    row_data.append(index.data())
                output.append(row_data)
            # Set Relays State
            if bool(output[0][2]):
                self.relay1checkBox.setChecked(True)
                self.set_relay("1", True)
            else:
                self.relay1checkBox.setChecked(False)
                self.set_relay("1", False)
            if bool(output[0][3]):
                self.relay2checkBox.setChecked(True)
                self.set_relay("2", True)
            else:
                self.relay2checkBox.setChecked(False)
                self.set_relay("2", False)
            if bool(output[0][4]):
                self.relay3checkBox.setChecked(True)
                self.set_relay("3", True)
            else:
                self.relay3checkBox.setChecked(False)
                self.set_relay("3", False)
            if bool(output[0][5]):
                self.relay4checkBox.setChecked(True)
                self.set_relay("4", True)
            else:
                self.relay4checkBox.setChecked(False)
                self.set_relay("4", False)
            # Move Action
            if self.current_position == 0:
                con.log(f"Move from 0 to {output[0][1]}")
                steps = round(int(output[0][1])) / 100
                for i in range(int(steps)):
                    self.moveTo(0, 100, self.speed)
                    self.current_position = int(self.current_position_label.text())
                    sleep(0.1)

            elif self.current_position > int(output[0][1]):
                difference = self.current_position - int(output[0][1])
                con.log(f"Move from {self.current_position} to {output[0][1]}")
                steps = round(int(difference) / 100)
                for i in range(int(steps)):
                    self.moveTo(1, 100, self.speed)
                    self.current_position = int(self.current_position_label.text())
                    sleep(0.1)

            else:
                difference = int(output[0][1]) - self.current_position
                con.log(f"Move from {self.current_position} to {output[0][1]}")
                steps = round(int(difference) / 100)
                for i in range(int(steps)):
                    self.moveTo(0, 100, self.speed)
                    sleep(0.1)
                    self.current_position = int(self.current_position_label.text())

    def getValue(self, value):
        self.current_treeIndex = value

    def addButton_click(self):
        self.add_dialog.set_fields_values(
            "Діапазон", self.current_position_label.text(), self.relay1, self.relay2, self.relay3, self.relay4, ""
            )
        answer = self.add_dialog.exec()
        if answer:
            values = self.add_dialog.get_fields_values()
            self.addTreeItem(
                self.model, values['band'], values['step'], bool(values['relay1']), bool(values['relay2']),
                bool(values['relay3']), bool(values['relay4']), values['desc']
                )
        else:
            con.log("Cancel")

    def get_info(self):
        if self.connected:
            resp = requests.get(self.url + self.api_status)
            json = resp.json()
            if 'step_count' in json:
                self.current_position_label.setText(str(json['step_count']))
                self.current_position = int(json['step_count'])
                self.max_position = int(json['max_position'])
            if 'status' in json:
                self.status_label.setText(F"Статус: {json['status']}")
        else:
            self.statusbar.showMessage("Не з'єднано")

    def mainTimer(self):
        gc.collect()
        mem = gc.get_stats()
        con.log("Garbage collect", justify = "center")
        con.log(f"{mem}")
        # suma = summary.summarize(self.all_objects)
        total = summary.getsizeof(self.all_objects)
        # summary.print_(suma)
        con.out(F"{total} bytes")

    def moveTo(self, direction, step, speed):
        if self.connected:
            json = {'dir': direction, 'step': step, 'speed': speed}
            resp = requests.post(self.url + self.api_move, json = json)
            json = resp.json()
            if 'step_count' in json:
                self.current_position_label.setText(str(json['step_count']))
            if 'status' in json:
                self.status_label.setText(F"Статус: {json['status']}")

    def setStylesheet(self, filename):
        with open(filename, "r") as fh:
            self.setStyleSheet(fh.read())

    def comboInit(self):
        step_items = ["10", "20", "50", "100", "200", "500"]
        speed_items = ["10", "15"]
        self.step_comboBox.addItems(step_items)
        self.step_comboBox.currentIndexChanged.connect(self.step_change)
        self.speed_comboBox.addItems(speed_items)
        self.speed_comboBox.currentIndexChanged.connect(self.speed_change)

    def parkButton_click(self):
        if self.connected:
            resp = requests.get(self.url + self.api_park)
            json = resp.json()
            if 'step_count' in json:
                con.log(F"step_count: {json['step_count']}")
                self.current_position_label.setText(str(json['step_count']))
                self.current_position = int(json['step_count'])
            if 'status' in json:
                self.status_label.setText(F"Статус: {json['status']}")

    def upButton_click(self):
        self.moveTo(0, self.step, self.speed)

    def downButton_click(self):
        self.moveTo(1, self.step, self.speed)

    def step_change(self):
        self.step = self.step_comboBox.currentText()

    def speed_change(self):
        self.speed = self.speed_comboBox.currentText()

    def connectButton_click(self):
        self.url = self.url_lineEdit.text()
        json = self.connect(self.url).json()
        if 'ip' in json:
            self.statusbar.showMessage("З'єднано")
            self.connected = True
            self.setButtons(True)
            self.get_info()
        else:
            self.statusbar.showMessage("Error: No API found, check URI")
            self.connected = False
            self.setButtons(False)

    def closeEvent(self, event):
        con.log("[green]Closing[/]")
        self.store_defaults()
        con.log("Storing defaults")
        self.store_bandTree()
        con.log("Storing bands tree")
        event.accept()
        sys.exit()


def main():
    sys._excepthook = sys.excepthook
    sys.excepthook = extended_exception_hook
    app = QtWidgets.QApplication(sys.argv)
    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
