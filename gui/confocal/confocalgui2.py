# -*- coding: utf-8 -*-

"""
This file contains the Qudi GUI for general Confocal control.

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
import time

from core.module import Connector, ConfigOption, StatusVar
from qtwidgets.scan_plotwidget import ScanImageItem
from qtwidgets.scientific_spinbox import ScienDSpinBox
from gui.guibase import GUIBase
from gui.guiutils import ColorBar
from gui.colordefs import ColorScaleInferno
from gui.colordefs import QudiPalettePale as palette
from gui.fitsettings import FitParametersWidget
from qtpy import QtCore
from qtpy import QtGui
from qtpy import QtWidgets
from qtpy import uic


class ConfocalMainWindow(QtWidgets.QMainWindow):
    """ Create the Mainwindow based on the corresponding *.ui file. """

    sigKeyboardPressed = QtCore.Signal(QtCore.QEvent)

    def __init__(self):
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'ui_confocalgui2.ui')

        # Load it
        super().__init__()
        uic.loadUi(ui_file, self)
        return

    def keyPressEvent(self, event):
        """Pass the keyboard press event from the main window further. """
        self.sigKeyboardPressed.emit(event)
        super().keyPressEvent(event)
        return

    def mouseDoubleClickEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.action_utility_zoom.setChecked(not self.action_utility_zoom.isChecked())
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)
        return


class ScannerSettingDialog(QtWidgets.QDialog):
    """ Create the ScannerSettingsDialog window, based on the corresponding *.ui file."""
    def __init__(self):
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'ui_scanner_settings.ui')

        # Load it
        super().__init__()
        uic.loadUi(ui_file, self)
        return


class OptimizerSettingDialog(QtWidgets.QDialog):
    """ User configurable settings for the optimizer embedded in cofocal gui"""
    def __init__(self):
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'ui_optimizer_settings.ui')

        # Load it
        super().__init__()
        uic.loadUi(ui_file, self)
        return


class ConfocalGui(GUIBase):
    """ Main Confocal Class for xy and depth scans.
    """
    _modclass = 'ConfocalGui'
    _modtype = 'gui'

    # declare connectors
    scannerlogic = Connector(interface='ConfocalLogic')

    # config options for gui
    image_axes_padding = ConfigOption(name='image_axes_padding', default=0.02)
    default_position_unit_prefix = ConfigOption(name='default_position_unit_prefix', default=None)

    # status vars
    slider_small_step = StatusVar(name='slider_small_step', default=10e-9)
    slider_big_step = StatusVar(name='slider_big_step', default=100e-9)
    _window_state = StatusVar(name='window_state', default=None)
    _window_geometry = StatusVar(name='window_geometry', default=None)

    # signals
    sigStartOptimizer = QtCore.Signal(list, str)

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)

        # QMainWindow and QDialog child instances
        self._mw = None
        self._ssd = None
        self._osd = None

        # Plot items
        self.first_scan_image = None
        self.second_scan_image = None
        self.optimizer_2d_image = None
        self.optimizer_1d_plot = None
        self.optimizer_1d_fit_plot = None
        self.line_scan_plot = None

        # References to automatically generated GUI elements to control the scanner axes
        self.axes_control_widgets = None
        self.optimizer_settings_axes_widgets = None
        return

    def on_activate(self):
        """ Initializes all needed UI files and establishes the connectors.

        This method executes the all the inits for the differnt GUIs and passes
        the event argument from fysom to the methods.
        """
        # Initialize main window and dialogues
        self._ssd = ScannerSettingDialog()
        self._osd = OptimizerSettingDialog()
        self._mw = ConfocalMainWindow()

        # Configure widgets according to available scan axes
        self._generate_axes_control_widgets()
        self._generate_optimizer_axes_widgets()

        # Initialize dockwidgets to default view
        self.restore_default_view()

        # Try to restore window state and geometry
        if self._window_geometry is not None:
            if not self._mw.restoreGeometry(bytearray.fromhex(self._window_geometry)):
                self._window_geometry = None
                self.log.debug(
                    'Unable to restore previous window geometry. Falling back to default.')
        if self._window_state is not None:
            if not self._mw.restoreState(bytearray.fromhex(self._window_state)):
                self._window_state = None
                self.log.debug(
                    'Unable to restore previous window state. Falling back to default.')

        # Set input widget value ranges and units according to scanner constraints
        self.apply_scanner_constraints()

        # Create plot items and add them to the respective widgets
        self.first_scan_image = ScanImageItem(image=np.zeros((2,2)), axisOrder='row-major')
        self.second_scan_image = ScanImageItem(image=np.zeros((2, 2)), axisOrder='row-major')
        self.optimizer_2d_image = ScanImageItem(image=np.zeros((2, 2)), axisOrder='row-major')
        self.optimizer_1d_plot = pg.PlotDataItem(x=np.arange(10),
                                                 y=np.zeros(10),
                                                 pen=pg.mkPen(palette.c1, style=QtCore.Qt.DotLine),
                                                 symbol='o',
                                                 symbolPen=palette.c1,
                                                 symbolBrush=palette.c1,
                                                 symbolSize=7)
        self.optimizer_1d_fit_plot = pg.PlotDataItem(x=np.arange(10),
                                                     y=np.zeros(10),
                                                     pen=pg.mkPen(palette.c2))
        self.line_scan_plot = pg.PlotDataItem(x=np.arange(2),
                                              y=np.zeros(2),
                                              pen=pg.mkPen(palette.c1))
        self._mw.first_2d_scan_scanPlotWidget.addItem(self.first_scan_image)
        self._mw.second_2d_scan_scanPlotWidget.addItem(self.second_scan_image)
        self._mw.optimizer_first_scanPlotWidget.addItem(self.optimizer_2d_image)
        self._mw.optimizer_second_plotWidget.addItem(self.optimizer_1d_plot)
        self._mw.optimizer_second_plotWidget.addItem(self.optimizer_1d_fit_plot)
        self._mw.line_scan_plotWidget.addItem(self.line_scan_plot)

        # Add crosshairs to the desired scan widgets
        self._mw.first_2d_scan_scanPlotWidget.toggle_crosshair(True, movable=True)
        self._mw.first_2d_scan_scanPlotWidget.set_crosshair_min_size_factor(0.02)
        self._mw.second_2d_scan_scanPlotWidget.toggle_crosshair(True, movable=True)
        self._mw.second_2d_scan_scanPlotWidget.set_crosshair_min_size_factor(0.02)
        self._mw.optimizer_first_scanPlotWidget.toggle_crosshair(True, movable=False)

        # Lock aspect ratios
        self._mw.first_2d_scan_scanPlotWidget.setAspectLocked(lock=True, ratio=1.0)
        self._mw.second_2d_scan_scanPlotWidget.setAspectLocked(lock=True, ratio=1.0)
        self._mw.optimizer_first_scanPlotWidget.setAspectLocked(lock=True, ratio=1.0)

        # Initialize widget values
        self.scanner_settings_updated()
        self.scanner_position_updated()
        self.scan_data_updated()

        self.init_main()      # initialize the main GUI
        self.init_scanner_settings()  # initialize the scanner settings dialogue
        self.init_optimizer_settings()  # initialize the optimizer settings dialogue
        self.init_display_settings()  # initialize the display settings dialogue
        return

    def init_main(self):
        """
        Definition, configuration and initialisation of the confocal GUI.

        This init connects all the graphic modules, which were created in the *.ui file and
        configures the event handling between the modules. Moreover it sets default values and
        constraints.
        """





        self.show()


        # self.update_scan_data(self.scannerlogic().scan_data)
        # self.update_scanner_position(self.scannerlogic().scanner_position)

        # set up scan line plot
        sc = self._scanning_logic._scan_counter
        sc = sc - 1 if sc >= 1 else sc
        if self._scanning_logic._zscan:
            data = self._scanning_logic.depth_image[sc, :, 0:4:3]
        else:
            data = self._scanning_logic.xy_image[sc, :, 0:4:3]

        self.scan_line_plot = pg.PlotDataItem(data, pen=pg.mkPen(palette.c1))
        self._mw.scanLineGraphicsView.addItem(self.scan_line_plot)

        ###################################################################
        #               Configuration of the optimizer tab                #
        ###################################################################
        # Load the image for the optimizer tab
        self.xy_refocus_image = ScanImageItem(
            image=self._optimizer_logic.xy_refocus_image[:, :, 3 + self.opt_channel],
            axisOrder='row-major')
        self.xy_refocus_image.set_image_extent(((self._optimizer_logic._initial_pos_x - 0.5 * self._optimizer_logic.refocus_XY_size,
                                                 self._optimizer_logic._initial_pos_x + 0.5 * self._optimizer_logic.refocus_XY_size),
                                                (self._optimizer_logic._initial_pos_y - 0.5 * self._optimizer_logic.refocus_XY_size,
                                                 self._optimizer_logic._initial_pos_y + 0.5 * self._optimizer_logic.refocus_XY_size)))

        self.depth_refocus_image = pg.PlotDataItem(
            x=self._optimizer_logic._zimage_Z_values,
            y=self._optimizer_logic.z_refocus_line[:, self._optimizer_logic.opt_channel],
            pen=pg.mkPen(palette.c1, style=QtCore.Qt.DotLine),
            symbol='o',
            symbolPen=palette.c1,
            symbolBrush=palette.c1,
            symbolSize=7
        )
        self.depth_refocus_fit_image = pg.PlotDataItem(
            x=self._optimizer_logic._fit_zimage_Z_values,
            y=self._optimizer_logic.z_fit_data,
            pen=pg.mkPen(palette.c2)
        )

        # Add the display item to the xy and depth ViewWidget, which was defined in the UI file.
        self._mw.xy_refocus_ViewWidget_2.addItem(self.xy_refocus_image)
        self._mw.depth_refocus_ViewWidget_2.addItem(self.depth_refocus_image)

        # Labelling axes
        self._mw.xy_refocus_ViewWidget_2.setLabel('bottom', 'X position', units='m')
        self._mw.xy_refocus_ViewWidget_2.setLabel('left', 'Y position', units='m')

        self._mw.depth_refocus_ViewWidget_2.addItem(self.depth_refocus_fit_image)

        self._mw.depth_refocus_ViewWidget_2.setLabel('bottom', 'Z position', units='m')
        self._mw.depth_refocus_ViewWidget_2.setLabel('left', 'Fluorescence', units='c/s')

        # Add crosshair to the xy refocus scan
        self._mw.xy_refocus_ViewWidget_2.toggle_crosshair(True, movable=False)
        self._mw.xy_refocus_ViewWidget_2.set_crosshair_pos((self._optimizer_logic._initial_pos_x,
                                                        self._optimizer_logic._initial_pos_y))

        # Set the state button as ready button as default setting.
        self._mw.action_stop_scanning.setEnabled(False)
        self._mw.action_scan_xy_resume.setEnabled(False)
        self._mw.action_scan_depth_resume.setEnabled(False)

        # Add the display item to the xy and depth ViewWidget, which was defined
        # in the UI file:
        self._mw.xy_ViewWidget.addItem(self.xy_image)
        self._mw.depth_ViewWidget.addItem(self.depth_image)

        # Label the axes:
        self._mw.xy_ViewWidget.setLabel('bottom', 'X position', units='m')
        self._mw.xy_ViewWidget.setLabel('left', 'Y position', units='m')
        self._mw.depth_ViewWidget.setLabel('bottom', 'X position', units='m')
        self._mw.depth_ViewWidget.setLabel('left', 'Z position', units='m')

        # Create crosshair for xy image:
        self._mw.xy_ViewWidget.toggle_crosshair(True, movable=True)
        self._mw.xy_ViewWidget.set_crosshair_min_size_factor(0.02)
        self._mw.xy_ViewWidget.set_crosshair_pos((ini_pos_x_crosshair, ini_pos_y_crosshair))
        self._mw.xy_ViewWidget.set_crosshair_size(
            (self._optimizer_logic.refocus_XY_size, self._optimizer_logic.refocus_XY_size))
        # connect the drag event of the crosshair with a change in scanner position:
        self._mw.xy_ViewWidget.sigCrosshairDraggedPosChanged.connect(self.update_from_roi_xy)

        # Set up and connect xy channel combobox
        scan_channels = self._scanning_logic.get_scanner_count_channels()
        for n, ch in enumerate(scan_channels):
            self._mw.xy_channel_ComboBox.addItem(str(ch), n)

        self._mw.xy_channel_ComboBox.activated.connect(self.update_xy_channel)

        # Create crosshair for depth image:
        self._mw.depth_ViewWidget.toggle_crosshair(True, movable=True)
        self._mw.depth_ViewWidget.set_crosshair_min_size_factor(0.02)
        self._mw.depth_ViewWidget.set_crosshair_pos((ini_pos_x_crosshair, ini_pos_z_crosshair))
        self._mw.depth_ViewWidget.set_crosshair_size(
            (self._optimizer_logic.refocus_XY_size, self._optimizer_logic.refocus_Z_size))
        # connect the drag event of the crosshair with a change in scanner position:
        self._mw.depth_ViewWidget.sigCrosshairDraggedPosChanged.connect(self.update_from_roi_depth)

        # Set up and connect depth channel combobox
        scan_channels = self._scanning_logic.get_scanner_count_channels()
        for n, ch in enumerate(scan_channels):
            self._mw.depth_channel_ComboBox.addItem(str(ch), n)



        # history actions
        self._mw.actionForward.triggered.connect(self._scanning_logic.history_forward)
        self._mw.actionBack.triggered.connect(self._scanning_logic.history_back)
        self._scanning_logic.signal_history_event.connect(lambda: self.set_history_actions(True))
        self._scanning_logic.signal_history_event.connect(self.update_xy_cb_range)
        self._scanning_logic.signal_history_event.connect(self.update_depth_cb_range)
        self._scanning_logic.signal_history_event.connect(self._mw.xy_ViewWidget.autoRange)
        self._scanning_logic.signal_history_event.connect(self._mw.depth_ViewWidget.autoRange)
        self._scanning_logic.signal_history_event.connect(self.update_scan_range_inputs)
        self._scanning_logic.signal_history_event.connect(self.change_x_image_range)
        self._scanning_logic.signal_history_event.connect(self.change_y_image_range)
        self._scanning_logic.signal_history_event.connect(self.change_z_image_range)



        ###################################################################
        #               Icons for the scan actions                        #
        ###################################################################

        self._scan_xy_single_icon = QtGui.QIcon()
        self._scan_xy_single_icon.addPixmap(
            QtGui.QPixmap("artwork/icons/qudiTheme/22x22/scan-xy-start.png"),
            QtGui.QIcon.Normal,
            QtGui.QIcon.Off)

        self._scan_depth_single_icon = QtGui.QIcon()
        self._scan_depth_single_icon.addPixmap(
            QtGui.QPixmap("artwork/icons/qudiTheme/22x22/scan-depth-start.png"),
            QtGui.QIcon.Normal,
            QtGui.QIcon.Off)

        self._scan_xy_loop_icon = QtGui.QIcon()
        self._scan_xy_loop_icon.addPixmap(
            QtGui.QPixmap("artwork/icons/qudiTheme/22x22/scan-xy-loop.png"),
            QtGui.QIcon.Normal,
            QtGui.QIcon.Off)

        self._scan_depth_loop_icon = QtGui.QIcon()
        self._scan_depth_loop_icon.addPixmap(
            QtGui.QPixmap("artwork/icons/qudiTheme/22x22/scan-depth-loop.png"),
            QtGui.QIcon.Normal,
            QtGui.QIcon.Off)

        self._mw.sigKeyboardPressed.connect(self.keyPressEvent)
        self.show()

    def initSettingsUI(self):
        """ Definition, configuration and initialisation of the settings GUI.

        This init connects all the graphic modules, which were created in the
        *.ui file and configures the event handling between the modules.
        Moreover it sets default values if not existed in the logic modules.
        """

        # Connect the action of the settings window with the code:
        self._sd.accepted.connect(self.update_settings)
        self._sd.rejected.connect(self.keep_former_settings)
        self._sd.buttonBox.button(QtWidgets.QDialogButtonBox.Apply).clicked.connect(self.update_settings)
        self._sd.hardware_switch.clicked.connect(self.switch_hardware)

        # write the configuration to the settings window of the GUI.
        self.keep_former_settings()

    def initOptimizerSettingsUI(self):
        """ Definition, configuration and initialisation of the optimizer settings GUI.

        This init connects all the graphic modules, which were created in the
        *.ui file and configures the event handling between the modules.
        Moreover it sets default values if not existed in the logic modules.
        """
        # Create the Settings window
        self._osd = OptimizerSettingDialog()
        # Connect the action of the settings window with the code:
        self._osd.accepted.connect(self.update_optimizer_settings)
        self._osd.rejected.connect(self.keep_former_optimizer_settings)
        self._osd.buttonBox.button(QtWidgets.QDialogButtonBox.Apply).clicked.connect(self.update_optimizer_settings)

        # Set up and connect xy channel combobox
        scan_channels = self._optimizer_logic.get_scanner_count_channels()
        for n, ch in enumerate(scan_channels):
            self._osd.opt_channel_ComboBox.addItem(str(ch), n)

        # Generation of the fit params tab ##################
        self._osd.fit_tab = FitParametersWidget(self._optimizer_logic.z_params)
        self._osd.settings_tabWidget.addTab(self._osd.fit_tab, "Fit Params")

        # write the configuration to the settings window of the GUI.
        self.keep_former_optimizer_settings()

    def on_deactivate(self):
        """ Reverse steps of activation

        @return int: error code (0:OK, -1:error)
        """
        self._window_geometry = bytearray(self._mw.saveGeometry()).hex()
        self._window_state = bytearray(self._mw.saveState()).hex()
        self._mw.close()
        return 0

    def show(self):
        """Make main window visible and put it above all other windows. """
        # Show the Main Confocal GUI:
        self._mw.show()
        self._mw.activateWindow()
        self._mw.raise_()

    def _generate_axes_control_widgets(self):
        font = QtGui.QFont()
        font.setBold(True)
        layout = self._mw.axes_control_gridLayout

        # Remove old widgets if present
        if self.axes_control_widgets:
            for widget_dict in self.axes_control_widgets.values():
                for widget in widget_dict.values():
                    layout.removeWidget(widget)

        self.axes_control_widgets = dict()
        for index, axis_name in enumerate(self.scannerlogic().scanner_axes_names, 1):
            if index == 1:
                label = self._mw.axis_0_label
                label.setFont(font)
                label.setText('{0}-Axis:'.format(axis_name))
                res_spinbox = self._mw.axis_0_resolution_spinBox
                min_spinbox = self._mw.axis_0_min_range_scienDSpinBox
                max_spinbox = self._mw.axis_0_max_range_scienDSpinBox
                slider = self._mw.axis_0_slider
                pos_spinbox = self._mw.axis_0_position_scienDSpinBox
            else:
                label = QtWidgets.QLabel('{0}-Axis:'.format(axis_name))
                label.setFont(font)
                label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)

                res_spinbox = QtWidgets.QSpinBox()
                res_spinbox.setRange(2, 2 ** 31 - 1)
                res_spinbox.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
                res_spinbox.setMinimumSize(50, 0)
                res_spinbox.setSizePolicy(QtWidgets.QSizePolicy.Preferred,
                                          QtWidgets.QSizePolicy.Preferred)

                min_spinbox = ScienDSpinBox()
                min_spinbox.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
                min_spinbox.setMinimumSize(75, 0)
                min_spinbox.setSizePolicy(QtWidgets.QSizePolicy.Preferred,
                                          QtWidgets.QSizePolicy.Preferred)

                max_spinbox = ScienDSpinBox()
                max_spinbox.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
                max_spinbox.setMinimumSize(75, 0)
                max_spinbox.setSizePolicy(QtWidgets.QSizePolicy.Preferred,
                                          QtWidgets.QSizePolicy.Preferred)

                slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
                slider.setMinimumSize(150, 0)
                slider.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

                pos_spinbox = ScienDSpinBox()
                pos_spinbox.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
                pos_spinbox.setMinimumSize(75, 0)
                pos_spinbox.setSizePolicy(QtWidgets.QSizePolicy.Preferred,
                                          QtWidgets.QSizePolicy.Preferred)

                # Add to layout
                layout.addWidget(label, index, 0)
                layout.addWidget(res_spinbox, index, 1)
                layout.addWidget(min_spinbox, index, 3)
                layout.addWidget(max_spinbox, index, 4)
                layout.addWidget(slider, index, 6)
                layout.addWidget(pos_spinbox, index, 7)

            # Remember widgets references for later access
            self.axes_control_widgets[axis_name] = dict()
            self.axes_control_widgets[axis_name]['label'] = label
            self.axes_control_widgets[axis_name]['res_spinbox'] = res_spinbox
            self.axes_control_widgets[axis_name]['min_spinbox'] = min_spinbox
            self.axes_control_widgets[axis_name]['max_spinbox'] = max_spinbox
            self.axes_control_widgets[axis_name]['slider'] = slider
            self.axes_control_widgets[axis_name]['pos_spinbox'] = pos_spinbox

        # layout.removeWidget(line)
        layout.addWidget(self._mw.line, 0, 2, -1, 1)
        layout.addWidget(self._mw.line_2, 0, 5, -1, 1)
        layout.setColumnStretch(5, 1)
        return

    def _generate_optimizer_axes_widgets(self):
        font = QtGui.QFont()
        font.setBold(True)
        layout = self._osd.scan_ranges_gridLayout

        # Remove old widgets if present
        if self.optimizer_settings_axes_widgets:
            for widget_dict in self.optimizer_settings_axes_widgets.values():
                for widget in widget_dict.values():
                    layout.removeWidget(widget)

        self.optimizer_settings_axes_widgets = dict()
        for index, axis_name in enumerate(self.scannerlogic().scanner_axes_names, 1):
            label_text = '{0}-Axis:'.format(axis_name)
            if index == 1:
                label = self._osd.axis_0_label
                label.setFont(font)
                label.setText(label_text)
                res_spinbox = self._osd.axis_0_optimizer_resolution_spinBox
                range_spinbox = self._osd.axis_0_optimizer_range_scienDSpinBox
            else:
                label = QtWidgets.QLabel(label_text)
                label.setFont(font)
                label.setAlignment(QtCore.Qt.AlignRight)

                range_spinbox = ScienDSpinBox()
                range_spinbox.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
                range_spinbox.setMinimumSize(70, 0)
                range_spinbox.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                                            QtWidgets.QSizePolicy.Preferred)

                res_spinbox = QtWidgets.QSpinBox()
                res_spinbox.setRange(2, 2 ** 31 - 1)
                res_spinbox.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
                res_spinbox.setMinimumSize(70, 0)
                res_spinbox.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                                          QtWidgets.QSizePolicy.Preferred)

                # Add to layout
                layout.addWidget(label, index, 0)
                layout.addWidget(range_spinbox, index, 1)
                layout.addWidget(res_spinbox, index, 2)

            # Remember widgets references for later access
            self.optimizer_settings_axes_widgets[axis_name] = dict()
            self.optimizer_settings_axes_widgets[axis_name]['label'] = label
            self.optimizer_settings_axes_widgets[axis_name]['range_spinbox'] = range_spinbox
            self.optimizer_settings_axes_widgets[axis_name]['res_spinbox'] = res_spinbox
        return

    def restore_default_view(self):
        """ Restore the arrangement of DockWidgets to default """
        self._mw.centralwidget.hide()
        self._mw.setDockNestingEnabled(True)

        # Show/hide dock widgets
        self._mw.first_scan_dockWidget.show()
        self._mw.second_scan_dockWidget.show()
        self._mw.optimizer_dockWidget.show()
        self._mw.scanner_control_dockWidget.show()
        self._mw.linescan_dockWidget.hide()
        self._mw.tilt_correction_dockWidget.hide()

        # re-dock any floating dock widgets
        self._mw.first_scan_dockWidget.setFloating(False)
        self._mw.second_scan_dockWidget.setFloating(False)
        self._mw.optimizer_dockWidget.setFloating(False)
        self._mw.scanner_control_dockWidget.setFloating(False)
        self._mw.linescan_dockWidget.setFloating(False)
        self._mw.tilt_correction_dockWidget.setFloating(False)

        self._mw.addDockWidget(QtCore.Qt.DockWidgetArea(1), self._mw.first_scan_dockWidget)
        self._mw.addDockWidget(QtCore.Qt.DockWidgetArea(2), self._mw.second_scan_dockWidget)
        self._mw.addDockWidget(QtCore.Qt.DockWidgetArea(2), self._mw.optimizer_dockWidget)
        self._mw.addDockWidget(QtCore.Qt.DockWidgetArea(2), self._mw.linescan_dockWidget)
        self._mw.addDockWidget(QtCore.Qt.DockWidgetArea(8), self._mw.scanner_control_dockWidget)
        self._mw.addDockWidget(QtCore.Qt.DockWidgetArea(8), self._mw.tilt_correction_dockWidget)
        return

    def apply_scanner_constraints(self):
        """ Set limits on input widgets according to scanner hardware constraints. """
        constraints = self.scannerlogic().scanner_constraints

        # Apply constraints for every scannner axis
        for index, (axis, axis_dict) in enumerate(constraints.items()):
            # Set value ranges
            res_range = (max(2, axis_dict['min_resolution']),
                         min(2**31-1, axis_dict['max_resolution']))
            self.axes_control_widgets[axis]['res_spinbox'].setRange(*res_range)
            self.axes_control_widgets[axis]['min_spinbox'].setRange(axis_dict['min_value'],
                                                                    axis_dict['max_value'])
            self.axes_control_widgets[axis]['max_spinbox'].setRange(axis_dict['min_value'],
                                                                    axis_dict['max_value'])
            self.axes_control_widgets[axis]['pos_spinbox'].setRange(axis_dict['min_value'],
                                                                    axis_dict['max_value'])
            self.axes_control_widgets[axis]['slider'].setRange(axis_dict['min_value'],
                                                               axis_dict['max_value'])
            self.optimizer_settings_axes_widgets[axis]['range_spinbox'].setRange(
                0, axis_dict['max_value'] - axis_dict['min_value'])
            self.optimizer_settings_axes_widgets[axis]['res_spinbox'].setRange(*res_range)
            # Set units as SpinBox suffix
            self.axes_control_widgets[axis]['min_spinbox'].setSuffix(axis_dict['unit'])
            self.axes_control_widgets[axis]['max_spinbox'].setSuffix(axis_dict['unit'])
            self.axes_control_widgets[axis]['pos_spinbox'].setSuffix(axis_dict['unit'])
            self.optimizer_settings_axes_widgets[axis]['range_spinbox'].setSuffix(axis_dict['unit'])

        # Apply general scanner constraints

        return

    @QtCore.Slot()
    @QtCore.Slot(dict)
    def scanner_settings_updated(self, settings=None):
        """
        Update scanner settings from logic and set widgets accordingly.

        @param dict settings: Settings dict containing the scanner settings to update.
                              If None (default) read the scanner setting from logic and update.
        """
        if not isinstance(settings, dict):
            settings = self.scannerlogic().scanner_settings

        if 'pixel_clock_frequency' in settings:
            self._ssd.pixel_clock_frequency_scienSpinBox.setValue(settings['pixel_clock_frequency'])
        if 'backscan_speed' in settings:
            self._ssd.backscan_speed_scienSpinBox.setValue(settings['backscan_speed'])
        if 'scan_resolution' in settings:
            for axis, resolution in settings['scan_resolution'].items():
                res_spinbox = self.axes_control_widgets[axis]['res_spinbox']
                res_spinbox.blockSignals(True)
                res_spinbox.setValue(resolution)
                res_spinbox.blockSignals(False)
        if 'scan_range' in settings:
            for axis, axis_range in settings['scan_range'].items():
                min_spinbox = self.axes_control_widgets[axis]['min_spinbox']
                max_spinbox = self.axes_control_widgets[axis]['max_spinbox']
                min_spinbox.blockSignals(True)
                max_spinbox.blockSignals(True)
                min_spinbox.setValue(axis_range[0])
                max_spinbox.setValue(axis_range[1])
                min_spinbox.blockSignals(False)
                max_spinbox.blockSignals(False)
        return

    @QtCore.Slot()
    @QtCore.Slot(dict)
    def scanner_position_updated(self, position=None):
        """
        Updates the scanner position and set widgets accordingly.

        @param dict position: The scanner position dict to update each axis position.
                              If None (default) read the scanner position from logic and update.
        """
        if not isinstance(position, dict):
            position = self.scannerlogic().scanner_position

        for axis, pos in position.items():
            slider = self.axes_control_widgets[axis]['slider']
            spinbox = self.axes_control_widgets[axis]['pos_spinbox']
            slider.blockSignals(True)
            spinbox.blockSignals(True)
            slider.setValue(pos)
            spinbox.setValue(pos)
            slider.blockSignals(False)
            spinbox.blockSignals(False)
        return

    @QtCore.Slot()
    @QtCore.Slot(dict)
    def scan_data_updated(self, scan_data=None):
        """

        @param dict scan_data:
        """
        if not isinstance(scan_data, dict):
            scan_data = self.scannerlogic().scan_data

        if len(scan_data) > 0:
            data = scan_data[0]
            if 'scan' in data:
                self.first_scan_image.setImage(image=data['scan'])# , levels=(cb_range[0], cb_range[1]))
            if 'axes' in data:
                x, y = data['axes']['names']
                x_unit, y_unit = data['axes']['units']
                self._mw.first_2d_scan_scanPlotWidget.setLabel('bottom', x, units=x_unit)
                self._mw.first_2d_scan_scanPlotWidget.setLabel('left', y, units=y_unit)
                self.first_scan_image.set_image_extent(data['axes']['extent'])
        if len(scan_data) > 1:
            data = scan_data[1]
            if 'scan' in data:
                self.second_scan_image.setImage(image=data['scan'])# , levels=(cb_range[0], cb_range[1]))
            if 'axes' in data:
                x, y = data['axes']['names']
                x_unit, y_unit = data['axes']['units']
                self._mw.second_2d_scan_scanPlotWidget.setLabel('bottom', x, units=x_unit)
                self._mw.second_2d_scan_scanPlotWidget.setLabel('left', y, units=y_unit)
                self.second_scan_image.set_image_extent(data['axes']['extent'])
        return

    def move_scanner_by_keyboard_event(self, event):
        """
        Handles the passed keyboard events from the main window.

        @param object event: qtpy.QtCore.QEvent object.
        """
        pass
        # modifiers = QtWidgets.QApplication.keyboardModifiers()
        # key = event.key()
        #
        # position = self._scanning_logic.get_position()   # in meters
        # x_pos = position[0]
        # y_pos = position[1]
        # z_pos = position[2]
        #
        # if modifiers == QtCore.Qt.ControlModifier:
        #     if key == QtCore.Qt.Key_Right:
        #         self.update_from_key(x=float(round(x_pos + self.slider_big_step, 10)))
        #     elif key == QtCore.Qt.Key_Left:
        #         self.update_from_key(x=float(round(x_pos - self.slider_big_step, 10)))
        #     elif key == QtCore.Qt.Key_Up:
        #         self.update_from_key(y=float(round(y_pos + self.slider_big_step, 10)))
        #     elif key == QtCore.Qt.Key_Down:
        #         self.update_from_key(y=float(round(y_pos - self.slider_big_step, 10)))
        #     elif key == QtCore.Qt.Key_PageUp:
        #         self.update_from_key(z=float(round(z_pos + self.slider_big_step, 10)))
        #     elif key == QtCore.Qt.Key_PageDown:
        #         self.update_from_key(z=float(round(z_pos - self.slider_big_step, 10)))
        #     else:
        #         event.ignore()
        # else:
        #     if key == QtCore.Qt.Key_Right:
        #         self.update_from_key(x=float(round(x_pos + self.slider_small_step, 10)))
        #     elif key == QtCore.Qt.Key_Left:
        #         self.update_from_key(x=float(round(x_pos - self.slider_small_step, 10)))
        #     elif key == QtCore.Qt.Key_Up:
        #         self.update_from_key(y=float(round(y_pos + self.slider_small_step, 10)))
        #     elif key == QtCore.Qt.Key_Down:
        #         self.update_from_key(y=float(round(y_pos - self.slider_small_step, 10)))
        #     elif key == QtCore.Qt.Key_PageUp:
        #         self.update_from_key(z=float(round(z_pos + self.slider_small_step, 10)))
        #     elif key == QtCore.Qt.Key_PageDown:
        #         self.update_from_key(z=float(round(z_pos - self.slider_small_step, 10)))
        #     else:
        #         event.ignore()
