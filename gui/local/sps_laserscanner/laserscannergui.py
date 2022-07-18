# -*- coding: utf-8 -*-
"""
This file contains the Qudi GUI module to operate the voltage (laser) scanner.

Qudi is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Qudi is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Qudi. If not, see <http://www.gnu.org/licenses/>.

Copyright (c) the Qudi Developers. See the COPYRIGHT.txt file at the
top-level directory of this distribution and at <https://github.com/Ulm-IQO/qudi/>
"""

import numpy as np
import os
import pyqtgraph as pg
from enum import Enum

from collections import OrderedDict
from core.connector import Connector
from gui.colordefs import ColorScaleInferno
from gui.guibase import GUIBase
from gui.guiutils import ColorBar
from qtpy import QtCore
from qtpy import QtGui
from qtpy import QtWidgets
from qtpy import uic
import time

from qtwidgets.scan_plotwidget import ScanImageItem
from core import config

class CustomScanMode(Enum):
    XYPLOT = 0
    AO = 1
    FUNCTION = 2

class CustomScanXYPlotValues(Enum):
    MINIMUM = 0
    MEAN = 1
    MAXIMUM = 2

class LaserScannerMainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'ui_laserscannergui.ui')

        # Load it
        super(LaserScannerMainWindow, self).__init__()
        uic.loadUi(ui_file, self)
        self.show()

class SettingDialog(QtWidgets.QDialog):
    """ Create the SettingsDialog window, based on the corresponding *.ui file."""

    def __init__(self):
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'ui_ls_settings.ui')

        # Load it
        super(SettingDialog, self).__init__()
        uic.loadUi(ui_file, self)

class SaveDialog(QtWidgets.QDialog):
    """ Dialog to provide feedback and block GUI while saving """
    def __init__(self, parent, title="Please wait", text="Saving..."):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowModality(QtCore.Qt.WindowModal)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)

        # Dialog layout
        self.text = QtWidgets.QLabel("<font size='16'>" + text + "</font>")
        self.hbox = QtWidgets.QHBoxLayout()
        self.hbox.addSpacerItem(QtWidgets.QSpacerItem(50, 0))
        self.hbox.addWidget(self.text)
        self.hbox.addSpacerItem(QtWidgets.QSpacerItem(50, 0))
        self.setLayout(self.hbox)

class LoadDialog(QtWidgets.QDialog):
    """ Dialog to provide feedback and block GUI while loading """
    def __init__(self, parent, title="Please wait", text="Loading..."):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowModality(QtCore.Qt.WindowModal)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)

        # Dialog layout
        self.text = QtWidgets.QLabel("<font size='16'>" + text + "</font>")
        self.hbox = QtWidgets.QHBoxLayout()
        self.hbox.addSpacerItem(QtWidgets.QSpacerItem(50, 0))
        self.hbox.addWidget(self.text)
        self.hbox.addSpacerItem(QtWidgets.QSpacerItem(50, 0))
        self.setLayout(self.hbox)

class LaserscannerGui(GUIBase):
    """ 
    """
    
    # declare connectors
    laserscannerlogic1 = Connector(interface='LaserScannerLogic')
    savelogic = Connector(interface='SaveLogic')


    sigStartScan = QtCore.Signal()
    sigStopScan = QtCore.Signal()
    sigChangeVoltage = QtCore.Signal(float)
    sigChangeRange = QtCore.Signal(list)
    sigChangeResolution = QtCore.Signal(float)
    sigChangeSpeed = QtCore.Signal(float)
    sigChangeLines = QtCore.Signal(int)
    sigSaveMeasurement = QtCore.Signal(str, list, list)



    def on_activate(self):
        """ Initializes all needed UI files and establishes the connectors.

        This method executes the all the inits for the differnt GUIs and passes
        the event argument from fysom to the methods.
        """
        # Getting an access to all connectors:
        self._scanning_logic = self.laserscannerlogic1()
        self._savelogic = self.savelogic()

        self.initMainUI()      # initialize the main GUI
        self.initSettingsUI()  # initialize the settings GUI

        self._save_dialog = SaveDialog(self._mw)
        self._load_dialog = LoadDialog(self._mw)      

    def initMainUI(self):
        """ Definition, configuration and initialisation of the laser scanner GUI.

        This init connects all the graphic modules, which were created in the
        *.ui file and configures the event handling between the modules.
        Moreover it sets default values.
        """
        self._mw = LaserScannerMainWindow()

        ###################################################################
        #               Configuring the dock widgets                      #
        ###################################################################
        # All our gui elements are dockable, and so there should be no "central" widget.
        self._mw.centralwidget.hide()
        self._mw.setDockNestingEnabled(True)

        # always use first channel on startup, can be changed afterwards
        self._channel = 0

        # init linenum
        self._linenum = self._scanning_logic._scan_counter

        # Get the image for the display from the logic
        raw_data_trace_scan_matrix= self._scanning_logic.trace_scan_matrix[:, :, 4 + self._channel]
        raw_data_retrace_scan_matrix = self._scanning_logic.retrace_scan_matrix[:, :, 4 + self._channel]
        raw_data_trace_plot_y_sum = self._scanning_logic.trace_plot_y_sum[self._channel,:]
        raw_data_trace_plot_y = self._scanning_logic.trace_plot_y[self._channel,:]
        raw_data_retrace_plot_y = self._scanning_logic.retrace_plot_y[self._channel,:]


        # Load the images in the display:
        self.trace_scan_matrix_image = pg.ImageItem(
            raw_data_trace_scan_matrix,
            axisOrder='row-major')

        self.trace_scan_matrix_image.setRect(
            QtCore.QRectF(
                self._scanning_logic.a_range[0],
                0,
                self._scanning_logic.a_range[1] - self._scanning_logic.a_range[0],
                self._scanning_logic._number_of_repeats)
        )

        self.retrace_scan_matrix_image = pg.ImageItem(
            raw_data_retrace_scan_matrix,
            axisOrder='row-major')

        self.retrace_scan_matrix_image.setRect(
            QtCore.QRectF(
                self._scanning_logic.a_range[0],
                0,
                self._scanning_logic.a_range[1] - self._scanning_logic.a_range[0],
                self._scanning_logic._number_of_repeats)
        )

        # self.trace_scan_matrix_image = ScanImageItem(image=raw_data_trace_scan_matrix, axisOrder='row-major')
        # self.retrace_scan_matrix_image = ScanImageItem(image=raw_data_retrace_scan_matrix, axisOrder='row-major')


        self.trace_plot_y_sum_image = pg.PlotDataItem(
            self._scanning_logic.plot_x,
            raw_data_trace_plot_y_sum)
        
        self.trace_plot_y_image = pg.PlotDataItem(
            self._scanning_logic.plot_x,
            raw_data_trace_plot_y)

        self.retrace_plot_y_image = pg.PlotDataItem(
            self._scanning_logic.plot_x,
            raw_data_retrace_plot_y)
        # Hide Retrace window
        self._mw.Retrace_dockWidget.hide()

        # Hide custom scan display
        self._mw.custom_scan_dockWidget.hide()
        
        # set cursor
        self.region_cursor = pg.LinearRegionItem([int(self._scanning_logic.a_range[0]), int(self._scanning_logic.a_range[1])], swapMode='block')
        self.region_cursor.setBounds([int(self._scanning_logic.a_range[0]), int(self._scanning_logic.a_range[1])])
        self.main_cursor = pg.InfiniteLine(pos = self._scanning_logic._current_a, angle = 90, movable = True, bounds = [int(self._scanning_logic.a_range[0]), int(self._scanning_logic.a_range[1])])



        # Add the display item to the VieWidget, which was defined in
        # the UI file.
        self._mw.trace_plot_y_sum_ViewWidget.addItem(self.trace_plot_y_sum_image)
        self._mw.trace_plot_y_sum_ViewWidget.showGrid(x=True, y=True, alpha=0.8)


        self._mw.trace_plot_y_ViewWidget.addItem(self.trace_plot_y_image)
        self._mw.trace_plot_y_ViewWidget.showGrid(x=True, y=True, alpha=0.8)

        self._mw.trace_scan_matrix_ViewWidget.addItem(self.trace_scan_matrix_image)


        self._mw.retrace_scan_matrix_ViewWidget.addItem(self.retrace_scan_matrix_image)
        self._mw.retrace_plot_y_ViewWidget.addItem(self.retrace_plot_y_image)
        self._mw.retrace_plot_y_ViewWidget.showGrid(x=True, y=True, alpha=0.8)

        # Set the state button as ready button as default setting.
        self._mw.action_resume.setEnabled(False)
        self._mw.action_stop_scanning.setEnabled(False)

        # Set up and connect channel combobox
        scan_channels = self._scanning_logic.get_scanner_count_channels()
        for n, ch in enumerate(scan_channels):
            self._mw.channel_ComboBox.addItem(str(ch), n)

        self._mw.channel_ComboBox.activated.connect(self.update_channel)

        # Take the default values from logic:
        self._mw.startDoubleSpinBox.setValue(self._scanning_logic._scan_range[0])
        self._mw.speedDoubleSpinBox.setValue(self._scanning_logic._scan_speed)
        self._mw.stopDoubleSpinBox.setValue(self._scanning_logic._scan_range[1])
        self._mw.cursorpositionDoubleSpinBox.setValue(self._scanning_logic._current_a)
        self._mw.resolutionSpinBox.setValue(self._scanning_logic._resolution)
        self._mw.noofrepeatsSpinBox.setValue(self._scanning_logic._number_of_repeats)
        self._mw.linenumspinBox.setValue(self._linenum)

        self._mw.clock_frequency_OutputWidget.setText('{0}'.format(round(self._scanning_logic._clock_frequency, 2)))

        # Update the inputed/displayed numbers if the cursor has left the field:
        self._mw.startDoubleSpinBox.editingFinished.connect(self.setRegionCursorPosition)
        self._mw.speedDoubleSpinBox.editingFinished.connect(self.change_speed)
        self._mw.stopDoubleSpinBox.editingFinished.connect(self.setRegionCursorPosition)
        self._mw.resolutionSpinBox.editingFinished.connect(self.change_resolution)
        self._mw.noofrepeatsSpinBox.editingFinished.connect(self.change_no_of_repeats)
        self._mw.cursorpositionDoubleSpinBox.editingFinished.connect(self.setCursorPosition)
        self._mw.linenumspinBox.editingFinished.connect(self.setLinenum)

        #################################################################
        #                           Actions                             #
        #################################################################
        # Connect the scan actions to the events if they are clicked. 
        self._mw.action_stop_scanning.triggered.connect(self.ready_clicked)

        self._scan_start_proxy = pg.SignalProxy(
            self._mw.action_scan_start.triggered,
            delay=0.1,
            slot=self.scan_start_clicked
            )
        self._resume_proxy =  pg.SignalProxy(
            self._mw.action_resume.triggered,
            delay=0.1,
            slot=self.continue_scan_clicked
            )
        self._custom_scan_start_proxy = pg.SignalProxy(
            self._mw.action_custom_scan_start.triggered,
            delay=0.1,
            slot=self.custom_scan_start_clicked
            )

        # Get initial custom scan values
        self._mw.actionCustom_scan_view.setChecked(
            self._scanning_logic._custom_scan)

        self._mw.sweeps_per_action_InputWidget.setValue(self._scanning_logic._custom_scan_sweeps_per_action)

        self._mw.x_ao0_min_doubleSpinBox.setValue(self._scanning_logic._custom_scan_x_range[0])
        self._mw.x_ao0_max_doubleSpinBox.setValue(self._scanning_logic._custom_scan_x_range[1])

        self._mw.y_ao1_min_doubleSpinBox.setValue(self._scanning_logic._custom_scan_y_range[0])
        self._mw.y_ao1_max_doubleSpinBox.setValue(self._scanning_logic._custom_scan_y_range[1])

        self._mw.z_ao2_min_doubleSpinBox.setValue(self._scanning_logic._custom_scan_z_range[0])
        self._mw.z_ao2_max_doubleSpinBox.setValue(self._scanning_logic._custom_scan_z_range[1])
    
        self._mw.x_ao0_order_InputWidget.setValue(self._scanning_logic._xyz_orders[0])
        self._mw.y_ao1_order_InputWidget.setValue(self._scanning_logic._xyz_orders[1])
        self._mw.z_ao2_order_InputWidget.setValue(self._scanning_logic._xyz_orders[2])

        if self._scanning_logic._custom_scan_mode.value == 0:
            self._mw.xy_plot_radioButton.setChecked(True)
        if self._scanning_logic._custom_scan_mode.value == 1:
            self._mw.custom_ao_radioButton.setChecked(True)
        if self._scanning_logic._custom_scan_mode.value == 2:
            self._mw.custom_function_radioButton.setChecked(True)

        # Connect custom scan buttons

        self._mw.xy_plot_radioButton.clicked.connect(self.custom_scan_xy_plot_radioButton_clicked)
        self._mw.custom_ao_radioButton.clicked.connect(self.custom_ao_radioButton_clicked)
        self._mw.custom_function_radioButton.clicked.connect(self.custom_function_radioButton_clicked)

        self._mw.sweeps_per_action_InputWidget.editingFinished.connect(self.SetSweepsPerAction)

        self._mw.x_ao0_min_doubleSpinBox.editingFinished.connect(self.change_custom_scan_x_range)
        self._mw.x_ao0_max_doubleSpinBox.editingFinished.connect(self.change_custom_scan_x_range)
        self._mw.y_ao1_min_doubleSpinBox.editingFinished.connect(self.change_custom_scan_y_range)
        self._mw.y_ao1_max_doubleSpinBox.editingFinished.connect(self.change_custom_scan_y_range)
        self._mw.z_ao2_min_doubleSpinBox.editingFinished.connect(self.change_custom_scan_z_range)
        self._mw.z_ao2_max_doubleSpinBox.editingFinished.connect(self.change_custom_scan_z_range)

        self._mw.x_ao0_order_InputWidget.editingFinished.connect(self.change_custom_scan_order)
        self._mw.y_ao1_order_InputWidget.editingFinished.connect(self.change_custom_scan_order)
        self._mw.z_ao2_order_InputWidget.editingFinished.connect(self.change_custom_scan_order)

        # Connect the buttons and inputs for colorbar
        self._mw.cb_manual_RadioButton.clicked.connect(self.update_cb_range)
        self._mw.cb_centiles_RadioButton.clicked.connect(self.update_cb_range)

        self._mw.cb_min_SpinBox.valueChanged.connect(self.shortcut_to_cb_manual)
        self._mw.cb_max_SpinBox.valueChanged.connect(self.shortcut_to_cb_manual)
        self._mw.cb_low_percentile_SpinBox.valueChanged.connect(self.shortcut_to_cb_centiles)
        self._mw.cb_high_percentile_SpinBox.valueChanged.connect(self.shortcut_to_cb_centiles)

        # Connect the emitted signal of an image change from the logic with
        self._scanning_logic.signal_trace_plots_updated.connect(self.refresh_trace_plots)
        self._scanning_logic.signal_retrace_plots_updated.connect(self.refresh_retrace_plots)

        # Connect the signal from the logic with an update
        self._scanning_logic.signal_change_position.connect(self.update_cursor_position_from_logic)
        self._scanning_logic.signal_custom_scan_range_updated.connect(self.update_custom_scan_range_input_from_logic)
        self._scanning_logic.signal_initialise_matrix.connect(self.initialise_matrix)


        # Connect other signals from the logic with an update of the gui

        self._scanning_logic.signal_start_scanning.connect(self.logic_started_scanning)
        self._scanning_logic.signal_save_started.connect(self.logic_started_save)
        self._scanning_logic.signal_data_saved.connect(self.logic_finished_save)
        self._scanning_logic.signal_continue_scanning.connect(self.logic_continued_scanning)
        self._scanning_logic.signal_clock_frequency_updated.connect(self.logic_clock_frequency_updated)

        # Connect the 'File' Menu dialog and the Settings window in confocal
        # with the methods:
        self._mw.action_Settings.triggered.connect(self.menu_settings)
        self._mw.actionSave_scan.triggered.connect(self.save_scan)
        self._mw.actionSave_configuration.triggered.connect(self.save_configuration)
        self._mw.actionLoad_configuration.triggered.connect(self.load_configuration)

        # full range action
        self._mw.action_full_range.triggered.connect(self.set_full_scan_range)

        # cursor signal
        self.region_cursor.sigRegionChanged.connect(self.updateSweepRange)
        self.main_cursor.sigPositionChanged.connect(self.updateCursorPosition)

        # history actions
        self._mw.actionForward.triggered.connect(self.history_forward_clicked)
        self._mw.actionBack.triggered.connect(self.history_back_clicked)
        self._scanning_logic.signal_history_event.connect(lambda: self.set_history_actions(True))
        self._scanning_logic.signal_history_event.connect(self.history_event)

        #################################################################
        #           Connect the colorbar and their actions              #
        #################################################################
        # Get the colorscales at set LUT
        my_colors = ColorScaleInferno()

        self.trace_scan_matrix_image.setLookupTable(my_colors.lut)
        self.retrace_scan_matrix_image.setLookupTable(my_colors.lut)

        # Create colorbars and add them at the desired place in the GUI. Add
        # also units to the colorbar.
        self.scan_cb = ColorBar(my_colors.cmap_normed, width = 100, cb_min = 0, cb_max = 100000)

        #adding colorbar to ViewWidget
        self._mw.cb_ViewWidget.addItem(self.scan_cb)
        self._mw.cb_ViewWidget.hideAxis('bottom')
        self._mw.cb_ViewWidget.hideAxis('left')
        self._mw.cb_ViewWidget.setLabel('right', 'Fluorescence', units='c/s')

        # all other components:
        self.enable_scan_actions()
        self.history_event()
        self.show()

    def initSettingsUI(self):
        """ Definition, configuration and initialisation of the settings GUI.

        This init connects all the graphic modules, which were created in the
        *.ui file and configures the event handling between the modules.
        Moreover it sets default values if not existed in the logic modules.
        """
        # Create the Settings window
        self._sd = SettingDialog()
        # Connect the action of the settings window with the code:
        self._sd.accepted.connect(self.update_settings)
        self._sd.rejected.connect(self.keep_former_settings)
        self._sd.buttonBox.button(QtWidgets.QDialogButtonBox.Apply).clicked.connect(self.update_settings)

        # write the configuration to the settings window of the GUI.
        self.keep_former_settings()


    def on_deactivate(self):
        """ Reverse steps of activation

        @return int: error code (0:OK, -1:error)
        """
        self._mw.close()
        return 0

    def update_settings(self):
        """ Write new settings from the gui to the file. """
        self._scanning_logic._smoothing_steps = self._sd.smoothing_steps_spinBox.value()
        self._scanning_logic._oneline_scanner_frequency = self._sd.cursor_frequency_spinBox.value()
        self._scanning_logic._goto_speed = self._sd.cursor_goto_speed_spinBox.value()
        if self._sd.min_radioButton.isChecked():
            self._scanning_logic._custom_scan_values = CustomScanXYPlotValues.MINIMUM
        if self._sd.mean_radioButton.isChecked():
            self._scanning_logic._custom_scan_values = CustomScanXYPlotValues.MEAN
        if self._sd.max_radioButton.isChecked():
            self._scanning_logic._custom_scan_values = CustomScanXYPlotValues.MAXIMUM
        self._scanning_logic._order_resolutions[0] = self._sd.order_1_resolution_spinBox.value()
        self._scanning_logic._order_resolutions[1] = self._sd.order_2_resolution_spinBox.value()
        self._scanning_logic._order_resolutions[2] = self._sd.order_3_resolution_spinBox.value()

    
    def keep_former_settings(self):
        self._sd.smoothing_steps_spinBox.setValue(self._scanning_logic._smoothing_steps)
        self._sd.cursor_frequency_spinBox.setValue(self._scanning_logic._oneline_scanner_frequency)
        self._sd.cursor_goto_speed_spinBox.setValue(self._scanning_logic._goto_speed)
        
        if self._scanning_logic._custom_scan_values.value == 0:
            self._sd.min_radioButton.setChecked(True)
        if self._scanning_logic._custom_scan_values.value == 1:
            self._sd.mean_radioButton.setChecked(True)
        if self._scanning_logic._custom_scan_values.value == 2:
            self._sd.max_radioButton.setChecked(True)
        self._sd.order_1_resolution_spinBox.setValue(self._scanning_logic._order_resolutions[0])
        self._sd.order_2_resolution_spinBox.setValue(self._scanning_logic._order_resolutions[1])
        self._sd.order_3_resolution_spinBox.setValue(self._scanning_logic._order_resolutions[2])


    def update_channel(self, index):
        """ The displayed channel for was changed, refresh the displayed image.

            @param index int: index of selected channel item in combo box
        """
        self._channel = int(self._mw.channel_ComboBox.itemData(index, QtCore.Qt.UserRole))
        self.refresh_trace_plots()
        self.refresh_retrace_plots()

    def update_custom_scan_range_input_from_logic(self):
        self._mw.x_ao0_min_doubleSpinBox.setValue(self._scanning_logic._custom_scan_x_range[0])
        self._mw.x_ao0_max_doubleSpinBox.setValue(self._scanning_logic._custom_scan_x_range[1])

        self._mw.y_ao1_min_doubleSpinBox.setValue(self._scanning_logic._custom_scan_y_range[0])
        self._mw.y_ao1_max_doubleSpinBox.setValue(self._scanning_logic._custom_scan_y_range[1])

        self._mw.z_ao2_min_doubleSpinBox.setValue(self._scanning_logic._custom_scan_z_range[0])
        self._mw.z_ao2_max_doubleSpinBox.setValue(self._scanning_logic._custom_scan_z_range[1])

        self._mw.x_ao0_order_InputWidget.setValue(self._scanning_logic._xyz_orders[0])
        self._mw.y_ao1_order_InputWidget.setValue(self._scanning_logic._xyz_orders[1])
        self._mw.z_ao2_order_InputWidget.setValue(self._scanning_logic._xyz_orders[2])



    def setLinenum(self):
        self._linenum = self._mw.linenumspinBox.value()
        if self._linenum not in range(0, self._scanning_logic._scan_counter + 1):
            self.log.error('Line num set value exceeds range.')
            return -1
        self._scanning_logic.trace_plot_y = self._scanning_logic.trace_scan_matrix[self._linenum-1, :, 4:].transpose()
        self._scanning_logic.retrace_plot_y = self._scanning_logic.retrace_scan_matrix[self._linenum-1, :, 4:].transpose()
        self.refresh_trace_plots()
        self.refresh_retrace_plots()

    def SetSweepsPerAction(self):
        self._scanning_logic._custom_scan_sweeps_per_action = int(self._mw.sweeps_per_action_InputWidget.value())

    def ready_clicked(self):
        """ Stop the scan if the state has switched to ready. """
        if self._scanning_logic.module_state() == 'locked':
            self._scanning_logic.stop_scanning()
        # Dissable the stop scanning button
        self._mw.action_stop_scanning.setEnabled(False)
        

    def scan_start_clicked(self):
        """ Manages what happens if the scan is started. """
        self.disable_scan_actions()
        self._scanning_logic.start_scanning(custom_scan = False, tag='gui')

    def continue_scan_clicked(self):
        """ Continue scan. """
        self.disable_scan_actions()
        self._scanning_logic.continue_scanning(tag = 'gui')

    def custom_scan_start_clicked(self):
        """ Start custom scan. """
        new_noofrepeats = self._scanning_logic._order_resolutions[0] * self._scanning_logic._order_resolutions[1] * self._scanning_logic._custom_scan_sweeps_per_action
        self._mw.noofrepeatsSpinBox.setValue(new_noofrepeats)
        self.change_no_of_repeats()
        self.disable_scan_actions()
        self._scanning_logic.start_scanning(custom_scan = True, tag='gui')

    def set_history_actions(self, enable):
        """ Enable or disable history arrows taking history state into account. """
        if enable and self._scanning_logic.history_index < len(self._scanning_logic.history) - 1:
            self._mw.actionForward.setEnabled(True)
        else:
            self._mw.actionForward.setEnabled(False)
        if enable and self._scanning_logic.history_index > 0:
            self._mw.actionBack.setEnabled(True)
        else:
            self._mw.actionBack.setEnabled(False)

    def history_forward_clicked(self):
        self.set_history_actions(False)
        self._scanning_logic.history_forward()
        self.set_history_actions(True)
    
    def history_back_clicked(self):
        self.set_history_actions(False)
        self._scanning_logic.history_back()
        self.set_history_actions(True)


    def update_cb_range(self): 
        """Redraw xcolour bar and scan image."""
        self.refresh_colorbar()
        self.refresh_trace_plots()
        self.refresh_retrace_plots()

    def update_parameters_from_logic(self):
        
        self._mw.startDoubleSpinBox.setValue(self._scanning_logic._scan_range[0])
        self._mw.speedDoubleSpinBox.setValue(self._scanning_logic._scan_speed)
        self._mw.stopDoubleSpinBox.setValue(self._scanning_logic._scan_range[1])
        self._mw.resolutionSpinBox.setValue(self._scanning_logic._resolution)
        self._mw.noofrepeatsSpinBox.setValue(self._scanning_logic._number_of_repeats)
        self._mw.linenumspinBox.setValue(self._scanning_logic._scan_counter)
        self._mw.elapsed_lines_DisplayWidget.display(self._scanning_logic._scan_counter)

        #cursor
        self.region_cursor.setRegion([self._mw.startDoubleSpinBox.value(),self._mw.stopDoubleSpinBox.value()])
        self.update_cursor_position_from_logic()
        self.update_custom_scan_range_input_from_logic()

    def custom_scan_xy_plot_radioButton_clicked(self):
        self._scanning_logic._custom_scan_mode = CustomScanMode.XYPLOT
        self._scanning_logic.get_confocal_scan_range()
        self._mw.x_ao0_order_InputWidget.setValue(1)
        self._mw.y_ao1_order_InputWidget.setValue(2)
        self._mw.x_ao0_order_InputWidget.setReadOnly(True)
        self._mw.y_ao1_order_InputWidget.setReadOnly(True)

        self.change_custom_scan_order()



    def custom_ao_radioButton_clicked(self):
        self._scanning_logic._custom_scan_mode = CustomScanMode.AO
        self._mw.x_ao0_order_InputWidget.setReadOnly(False)
        self._mw.y_ao1_order_InputWidget.setReadOnly(False)

    def custom_function_radioButton_clicked(self):
        self._scanning_logic._custom_scan_mode = CustomScanMode.FUNCTION

    def change_custom_scan_x_range(self):
        self._scanning_logic._custom_scan_x_range[0] = self._mw.x_ao0_min_doubleSpinBox.value()
        self._scanning_logic._custom_scan_x_range[1] = self._mw.x_ao0_max_doubleSpinBox.value()
        self._scanning_logic.update_confocal_scan_range()

    def change_custom_scan_y_range(self):
        self._scanning_logic._custom_scan_y_range[0] = self._mw.y_ao1_min_doubleSpinBox.value()
        self._scanning_logic._custom_scan_y_range[1] = self._mw.y_ao1_max_doubleSpinBox.value()
        self._scanning_logic.update_confocal_scan_range()

    def change_custom_scan_z_range(self):
        self._scanning_logic._custom_scan_z_range[0] = self._mw.z_ao2_min_doubleSpinBox.value()
        self._scanning_logic._custom_scan_z_range[1] = self._mw.z_ao2_max_doubleSpinBox.value()
        self._scanning_logic.update_confocal_scan_range()

    def change_custom_scan_order(self):
        self._scanning_logic._xyz_orders[0]= self._mw.x_ao0_order_InputWidget.value()
        self._scanning_logic._xyz_orders[1] = self._mw.y_ao1_order_InputWidget.value()
        self._scanning_logic._xyz_orders[2] = self._mw.z_ao2_order_InputWidget.value()


    def shortcut_to_cb_manual(self):
        self._mw.cb_manual_RadioButton.setChecked(True)
        self.update_cb_range()

    def shortcut_to_cb_centiles(self):
        self._mw.cb_centiles_RadioButton.setChecked(True)
        self.update_cb_range()

    def refresh_trace_plots(self):        
        """ Refresh the trace-matrix image """

        trace_image_data = self._scanning_logic.trace_scan_matrix[:self._scanning_logic._scan_counter, :, 4 + self._channel]
        cb_range = self.get_cb_range()
        
        # Now update image with new color scale, and update colorbar
        self.trace_scan_matrix_image.setImage(image=trace_image_data, levels=(cb_range[0], cb_range[1]))
        self.refresh_colorbar()


        _data_trace_plot_y_sum = self._scanning_logic.trace_plot_y_sum[self._channel,:]
        _data_trace_plot_y = self._scanning_logic.trace_plot_y[self._channel,:]

        # Refresh the xy-plot image
        self.trace_plot_y_sum_image.setData(self._scanning_logic.plot_x, _data_trace_plot_y_sum)
        self.trace_plot_y_image.setData(self._scanning_logic.plot_x, _data_trace_plot_y)

        # scan counter display
        self._mw.elapsed_lines_DisplayWidget.display(self._scanning_logic._scan_counter)


    def refresh_retrace_plots(self):
        """ Refresh the trace-matrix image """
        retrace_image_data = self._scanning_logic.retrace_scan_matrix[:self._scanning_logic._scan_counter, :, 4 + self._channel]
        cb_range = self.get_cb_range()

        # Now update image with new color scale, and update colorbar
        self.retrace_scan_matrix_image.setImage(image=retrace_image_data, levels=(cb_range[0], cb_range[1]))

        _data_retrace_plot_y = self._scanning_logic.retrace_plot_y[self._channel,:]
        # Refresh the xy-plot image
        self.retrace_plot_y_image.setData(self._scanning_logic.plot_x, _data_retrace_plot_y)

        # Unlock state widget if scan is finished
        if self._scanning_logic.module_state() != 'locked':
            self.enable_scan_actions()


    def update_cursor_position_from_logic(self):
        self._mw.cursorpositionDoubleSpinBox.setValue(self._scanning_logic._current_a)
        self.main_cursor.setValue(self._mw.cursorpositionDoubleSpinBox.value())
        

    def logic_started_scanning(self,tag):
        """ Disable icons if a scan was started.

            @param tag str: tag indicating command source
        """
        if tag == 'logic':
            self.disable_scan_actions()

    def logic_started_save(self):
        """ Displays modal dialog when save process starts """
        self._save_dialog.show()

    def logic_finished_save(self):
        """ Hides modal dialog when save process done """
        self._save_dialog.hide()

    def logic_continued_scanning(self,tag):
        """ Disable icons if a scan was continued.

            @param tag str: tag indicating command source
        """
        if tag == 'logic':
            self.disable_scan_actions()

    def logic_clock_frequency_updated(self):
        self._mw.clock_frequency_OutputWidget.setText('{0}'.format(round(self._scanning_logic._clock_frequency, 2)))

    def menu_settings(self):
        """ This method opens the settings menu. """
        self._sd.exec_()

    def save_scan(self):
        """ Run the save routine from the logic to save the data."""
        self._save_dialog.show()
        cb_range = self.get_cb_range()
        # Percentile range is None, unless the percentile scaling is selected in GUI.
        pcile_range = None
        if not self._mw.cb_manual_RadioButton.isChecked():
            low_centile = self._mw.cb_low_percentile_SpinBox.value()
            high_centile = self._mw.cb_high_percentile_SpinBox.value()
            pcile_range = [low_centile, high_centile]
        self._scanning_logic.save_data(colorscale_range=cb_range, percentile_range=pcile_range, block=False)


    def save_configuration(self):
        """ Save current statusvariable to the file"""
        defaultconfigpath = self._scanning_logic._save_logic.get_path_for_module(module_name='sps_laserscanner_cfg')
        filename = QtWidgets.QFileDialog.getSaveFileName(
            self._mw,
            'Save Configuration',
            defaultconfigpath,
            'Configuration files (*.cfg)')[0]

        if filename != '':
            self._save_dialog.show()
            self._scanning_logic.save_history_config()
            variables = self._scanning_logic.getStatusVariables()
            try:
                config.save(filename, variables)
                self._save_dialog.hide()
            except:
                self._save_dialog.hide()
                print(variables)
                self.log.exception('Failed to save status variables to {0}'.format(filename))

    def load_configuration(self):
        """ Load statusvariable to the program"""
        try:
            defaultconfigpath = self._scanning_logic._save_logic.get_path_for_module(module_name='sps_laserscanner_cfg')
            filename = QtWidgets.QFileDialog.getOpenFileName(
                self._mw,
                'Load Configuration',
                defaultconfigpath,
                'Configuration files (*.cfg)')[0]
            if filename != '':
                if os.path.isfile(filename):
                    self._load_dialog.show()
                    variables = config.load(filename)
                    self._load_dialog.hide()
                else:
                    variables = OrderedDict()
                self._scanning_logic.setStatusVariables(variables)
                self._scanning_logic.load_history_config()
        except:
            self.log.exception('Failed to load status variables from {0}'.format(filename))

    def set_full_scan_range(self):
        self._mw.startDoubleSpinBox.setValue(self._scanning_logic.a_range[0])
        self._mw.stopDoubleSpinBox.setValue(self._scanning_logic.a_range[1])
        self.setRegionCursorPosition()

    def enable_scan_actions(self):
        """ Reset the scan action buttons to the default active
        state when the system is idle.
        """
        # Dissable the stop scanning button
        self._mw.action_stop_scanning.setEnabled(False)

        # Disable the start scan buttons
        self._mw.action_scan_start.setEnabled(True)

        self._mw.action_custom_scan_start.setEnabled(True)
        self._mw.action_full_range.setEnabled(True)

        self.set_history_actions(True)

        if self._scanning_logic._scan_continuable is True:
            self._mw.action_resume.setEnabled(True)
        else:
            self._mw.action_resume.setEnabled(False)


        # Add the cursor to the plots
        self._mw.trace_plot_y_sum_ViewWidget.addItem(self.region_cursor)
        self._mw.trace_plot_y_ViewWidget.addItem(self.main_cursor)

        # Update the inputed/displayed numbers if the cursor has left the field:
        self._mw.startDoubleSpinBox.editingFinished.connect(self.setRegionCursorPosition)
        self._mw.speedDoubleSpinBox.editingFinished.connect(self.change_speed)
        self._mw.stopDoubleSpinBox.editingFinished.connect(self.setRegionCursorPosition)
        self._mw.resolutionSpinBox.editingFinished.connect(self.change_resolution)
        self._mw.noofrepeatsSpinBox.editingFinished.connect(self.change_no_of_repeats)
        self._mw.cursorpositionDoubleSpinBox.editingFinished.connect(self.setCursorPosition)

        # Connect custom scan buttons
        self._mw.xy_plot_radioButton.clicked.connect(self.custom_scan_xy_plot_radioButton_clicked)
        self._mw.custom_ao_radioButton.clicked.connect(self.custom_ao_radioButton_clicked)
        self._mw.custom_function_radioButton.clicked.connect(self.custom_function_radioButton_clicked)

        self._mw.sweeps_per_action_InputWidget.editingFinished.connect(self.SetSweepsPerAction)

        self._mw.x_ao0_min_doubleSpinBox.editingFinished.connect(self.change_custom_scan_x_range)
        self._mw.x_ao0_max_doubleSpinBox.editingFinished.connect(self.change_custom_scan_x_range)
        self._mw.y_ao1_min_doubleSpinBox.editingFinished.connect(self.change_custom_scan_y_range)
        self._mw.y_ao1_max_doubleSpinBox.editingFinished.connect(self.change_custom_scan_y_range)
        self._mw.z_ao2_min_doubleSpinBox.editingFinished.connect(self.change_custom_scan_z_range)
        self._mw.z_ao2_max_doubleSpinBox.editingFinished.connect(self.change_custom_scan_z_range)

        self._mw.x_ao0_order_InputWidget.editingFinished.connect(self.change_custom_scan_order)
        self._mw.y_ao1_order_InputWidget.editingFinished.connect(self.change_custom_scan_order)
        self._mw.z_ao2_order_InputWidget.editingFinished.connect(self.change_custom_scan_order)
        # full range action
        self._mw.action_full_range.triggered.connect(self.set_full_scan_range)

        # cursor signal
        self.region_cursor.sigRegionChanged.connect(self.updateSweepRange)
        self.main_cursor.sigPositionChanged.connect(self.updateCursorPosition)
        # line num
        self._mw.linenumspinBox.editingFinished.connect(self.setLinenum)

    def show(self):
        """Make main window visible and put it above all other windows. """
        # Show the Main Confocal GUI:
        self._mw.show()
        self._mw.activateWindow()
        self._mw.raise_()


    def updateSweepRange(self):
        self._mw.startDoubleSpinBox.setValue(int(self.region_cursor.getRegion()[0]))
        self._mw.stopDoubleSpinBox.setValue(int(self.region_cursor.getRegion()[1]))
        self.set_scan_range()


    def updateCursorPosition(self):
        """ Update the display of cursor position
        """
        self._mw.cursorpositionDoubleSpinBox.setValue(int(self.main_cursor.value()))
        self._scanning_logic.set_position(a=self._mw.cursorpositionDoubleSpinBox.value())
        self._scanning_logic._change_position()

    def setRegionCursorPosition(self):
        self.region_cursor.setRegion([self._mw.startDoubleSpinBox.value(),self._mw.stopDoubleSpinBox.value()])
        self.set_scan_range()

    def setCursorPosition(self):

        self._scanning_logic.set_position(a=self._mw.cursorpositionDoubleSpinBox.value())
        self._scanning_logic._change_position()
        self.main_cursor.setValue(self._mw.cursorpositionDoubleSpinBox.value())

    def get_cb_range(self):
        """ Determines the cb_min and cb_max values for the image
        """
        # If "Manual" is checked, or the image data is empty (all zeros), then take manual cb range.
        if self._mw.cb_manual_RadioButton.isChecked() or np.count_nonzero(self.trace_scan_matrix_image.image) < 1:
            cb_min = self._mw.cb_min_SpinBox.value()
            cb_max = self._mw.cb_max_SpinBox.value()

        # Otherwise, calculate cb range from percentiles.
        else:
            # Exclude any zeros (which are typically due to unfinished scan)
            image_nonzero = self.trace_scan_matrix_image.image[np.nonzero(self.trace_scan_matrix_image.image)]

            # Read centile range
            low_centile = self._mw.cb_low_percentile_SpinBox.value()
            high_centile = self._mw.cb_high_percentile_SpinBox.value()

            cb_min = np.percentile(image_nonzero, low_centile)
            cb_max = np.percentile(image_nonzero, high_centile)

        cb_range = [cb_min, cb_max]
        return cb_range
    
    def refresh_colorbar(self):
        """ Adjust the colorbar.

        Calls the refresh method from colorbar, which takes either the lowest
        and higherst value in the image or predefined ranges. Note that you can
        invert the colorbar if the lower border is bigger then the higher one.
        """
        cb_range = self.get_cb_range()
        self.scan_cb.refresh_colorbar(cb_range[0], cb_range[1])

    def disable_scan_actions(self):
        """ Disables the buttons for scanning.
        """
        # Ensable the stop scanning button
        self._mw.action_stop_scanning.setEnabled(True)

        # Disable the start scan buttons
        self._mw.action_scan_start.setEnabled(False)
        self._mw.action_resume.setEnabled(False)
        self._mw.action_custom_scan_start.setEnabled(False)
        self._mw.action_full_range.setEnabled(False)

        self.set_history_actions(False)
        
        # Remove the cursor to the plots
        self._mw.trace_plot_y_sum_ViewWidget.removeItem(self.region_cursor)
        self._mw.trace_plot_y_ViewWidget.removeItem(self.main_cursor)


        self._mw.startDoubleSpinBox.editingFinished.disconnect()
        self._mw.speedDoubleSpinBox.editingFinished.disconnect()
        self._mw.stopDoubleSpinBox.editingFinished.disconnect()
        self._mw.resolutionSpinBox.editingFinished.disconnect()
        self._mw.noofrepeatsSpinBox.editingFinished.disconnect()
        self._mw.cursorpositionDoubleSpinBox.editingFinished.disconnect()


        # Disconnect custom scan buttons

        self._mw.xy_plot_radioButton.clicked.disconnect()
        self._mw.custom_ao_radioButton.clicked.disconnect()
        self._mw.custom_function_radioButton.clicked.disconnect()

        self._mw.sweeps_per_action_InputWidget.editingFinished.disconnect()

        self._mw.x_ao0_min_doubleSpinBox.editingFinished.disconnect()
        self._mw.x_ao0_max_doubleSpinBox.editingFinished.disconnect()
        self._mw.y_ao1_min_doubleSpinBox.editingFinished.disconnect()
        self._mw.y_ao1_max_doubleSpinBox.editingFinished.disconnect()
        self._mw.z_ao2_min_doubleSpinBox.editingFinished.disconnect()
        self._mw.z_ao2_max_doubleSpinBox.editingFinished.disconnect()

        self._mw.x_ao0_order_InputWidget.editingFinished.disconnect()
        self._mw.y_ao1_order_InputWidget.editingFinished.disconnect()
        self._mw.z_ao2_order_InputWidget.editingFinished.disconnect()
        # full range action
        self._mw.action_full_range.triggered.disconnect()
    
        # cursor signal
        self.region_cursor.sigRegionChanged.disconnect()
        self.main_cursor.sigPositionChanged.disconnect()

        # line num
        self._mw.linenumspinBox.clear()
        self._mw.linenumspinBox.editingFinished.disconnect()

    def set_scan_range(self):
        scan_range = [self._mw.startDoubleSpinBox.value(), self._mw.stopDoubleSpinBox.value()]
        self._scanning_logic.set_scan_range(scan_range)

    def change_speed(self):
        self._scanning_logic.set_scan_speed(self._mw.speedDoubleSpinBox.value())
        
    def change_no_of_repeats(self):
        self._scanning_logic.set_number_of_repeats(self._mw.noofrepeatsSpinBox.value())

    def change_resolution(self):
        self._scanning_logic.set_resolution(self._mw.resolutionSpinBox.value())

    def initialise_matrix(self):
        raw_data_trace_scan_matrix= self._scanning_logic.trace_scan_matrix[:, :, 4 + self._channel]
        raw_data_retrace_scan_matrix = self._scanning_logic.retrace_scan_matrix[:, :, 4 + self._channel]
        # Load the images in the display:
        self.trace_scan_matrix_image.setImage(
            raw_data_trace_scan_matrix,
            axisOrder='row-major')

        self.trace_scan_matrix_image.setRect(
            QtCore.QRectF(
                self._scanning_logic._scan_range[0],
                0,
                self._scanning_logic._scan_range[1] - self._scanning_logic._scan_range[0],
                self._scanning_logic._number_of_repeats)
        )

        self.retrace_scan_matrix_image.setImage(
            raw_data_retrace_scan_matrix,
            axisOrder='row-major')

        self.retrace_scan_matrix_image.setRect(
            QtCore.QRectF(
                self._scanning_logic._scan_range[0],
                0,
                self._scanning_logic._scan_range[1] - self._scanning_logic._scan_range[0],
                self._scanning_logic._number_of_repeats)
        )

    def history_event(self):
        self.initialise_matrix()    
        self.update_parameters_from_logic()
        self.update_cb_range()






    


