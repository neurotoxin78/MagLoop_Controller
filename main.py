import gc
import sys
import json as jconf
import requests
from PyQt6 import QtCore, QtWidgets, uic
from PyQt6.QtGui import QStandardItemModel
from PyQt6.QtCore import Qt
from time import sleep
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
        uic.loadUi('add_dialog.ui', self)

    def set_fields_values(self, band, step, relay, desc):
        self.bandlineEdit.setText(band)
        self.steplineEdit.setText(step)
        self.desclineEdit.setText(desc)
        self.relay1checkBox.setChecked(bool(relay))

    def get_fields_values(self):
        band = self.bandlineEdit.text()
        step = self.steplineEdit.text()
        desc = self.desclineEdit.text()
        relay = self.relay1checkBox.isChecked()
        return {"band": band, "step": step, "relay": relay, "desc": desc}


class MainWindow(QtWidgets.QMainWindow):
    BAND, STEPS, RELAY, DESCRIPTION = range(4)

    def __init__(self, *args, **kwargs):
        super(MainWindow, self).__init__(*args, **kwargs)
        # Load the UI Page
        uic.loadUi('ui.ui', self)
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
        self.connected = False
        self.direction = None
        self.step = None
        self.relay = True
        self.speed = None
        self.current_position = None
        self.max_position = None
        self.api_status = None
        self.api_park = None
        self.api_move = None
        self.api_relay = None
        self.url = None
        self.autocon = False
        self.current_treeIndex = 0
        self.initUI()
        self.configure()
        self.bandTreeViewConfig()
        self.load_bandTree()
        self.autoconnect()
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
        self.relay1checkBox.toggled.connect(self.set_relay)
        self.comboInit()
        con.log(F"UI Initialized")
    def set_relay(self):
        if self.connected:
            self.relay = self.relay1checkBox.isChecked()
            if self.relay:
                json = {'switch': "0"}
                #self.relay = True
            else:
                json = {'switch': "1"}
                #self.relay = False
            resp = requests.post(self.url + self.api_relay, json=json)
            json = resp.json()
            if 'status' in json:
                stat = json["status"]
                self.relay1_status_label.setText(F"1: {stat}")
            # if 'status' in json:
            #     self.status_label.setText(F"Статус: {json['status']}")

    def autoconnect(self):
        self.autocon = self.autoConCheckBox.isChecked()
        if self.autocon:
            self.connectButton_click()

    def set_autoconnect(self):
        self.autocon = self.autoConCheckBox.isChecked()
        con.log(F"Set autoconnect: {self.autocon}")

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
                self.addTreeItem(self.model, bands[key]['band'], bands[key]['step'], bands[key]['relay'], bands[key]['desc'])
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
                        d_dict['bands'][row]['relay'] = bool(self.model.data(index))
                    case 3:
                        d_dict['bands'][row]['desc'] = str(self.model.data(index))
        with open("bands.json", "w") as fp:
            jconf.dump(d_dict, fp)

    def store_defaults(self):
        defaults = {"defaults": {"step": self.step, "speed": self.speed, "autoconnect": self.autocon, "relay": self.relay}}
        defaults = jconf.dumps(defaults, indent=4)
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
            self.relay = d["relay"]
            step_index = self.step_comboBox.findText(self.step)
            self.step_comboBox.setCurrentIndex(step_index)
            speed_index = self.speed_comboBox.findText(self.speed)
            self.speed_comboBox.setCurrentIndex(speed_index)
            con.log(F"Autoconnect: {bool(d['autoconnect'])}")
            if bool(d['autoconnect']):
                self.autoConCheckBox.setChecked(True)
            if bool(d['relay']):
                self.relay1checkBox.setChecked(True)
                self.relay1_status_label.setText(F"1: ON")
            con.log(F"Loaded defaults")
        else:
            raise KeyError("Error: Key 'defaults' not found in config file.")

    def bandTreeViewConfig(self):
        self.bandtreeView.setRootIsDecorated(False)
        self.bandtreeView.setAlternatingRowColors(True)
        self.model = self.createBandTreeModel(self)
        self.bandtreeView.setModel(self.model)
        self.bandtreeView.setSortingEnabled(True)
        self.bandtreeView.setColumnWidth(0, 85)
        self.bandtreeView.setColumnWidth(1, 50)
        self.bandtreeView.setColumnWidth(2, 50)

    def createBandTreeModel(self, parent):
        model = QStandardItemModel(0, 4, parent)
        model.setHeaderData(self.BAND, Qt.Orientation.Horizontal, "Діапазон")
        model.setHeaderData(self.STEPS, Qt.Orientation.Horizontal, "Кроки")
        model.setHeaderData(self.RELAY, Qt.Orientation.Horizontal, "Реле")
        model.setHeaderData(self.DESCRIPTION, Qt.Orientation.Horizontal, "Опис")
        return model

    def addTreeItem(self, model, band, steps, relay, desc):
        model.insertRow(0)
        model.setData(model.index(0, self.BAND), band)
        model.setData(model.index(0, self.STEPS), steps)
        model.setData(model.index(0, self.RELAY), relay)
        model.setData(model.index(0, self.DESCRIPTION), desc)
        con.log(F"Added items Band: {band}, Step : {steps}, Relay : {relay} Description: {desc}")



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
            # Set Relay State
            if bool(output[0][2]):
                # print(output[0][2])
                self.relay1checkBox.setChecked(True)
                self.set_relay()
            else:
                self.relay1checkBox.setChecked(False)
                self.set_relay()
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
        self.add_dialog.set_fields_values("Діапазон", self.current_position_label.text(), self.relay, "")
        answer = self.add_dialog.exec()
        if answer:
            values = self.add_dialog.get_fields_values()
            self.addTreeItem(self.model, values['band'], values['step'], bool(values['relay']), values['desc'])
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

    @staticmethod
    def mainTimer():
        gc.collect()
        mem = gc.get_stats()
        con.log("Garbage collect", justify="center")
        con.print(mem)

    def moveTo(self, direction, step, speed):
        if self.connected:
            json = {'dir': direction, 'step': step, 'speed': speed}
            resp = requests.post(self.url + self.api_move, json=json)
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
            self.get_info()
        else:
            self.statusbar.showMessage("Error: No API found, check URI")
            self.connected = False

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
