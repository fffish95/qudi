# -*- coding: utf-8 -*-

from typing import Text
import numpy as np
import os

from core.connector import Connector
from gui.guibase import GUIBase
from gui.colordefs import QudiPalettePale as palette
from qtpy import QtWidgets
from qtpy import QtCore
from qtpy import uic
import time
import pyqtgraph as pg

class LocalLaserScannerMainWindow(QtWidgets.QMainWindow):
    """ Create the Main Window based on the *.ui file. """

    def __init__(self):
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'ui_locallaserscanner.ui')

        # Load it
        super().__init__()
        uic.loadUi(ui_file, self)
        self.show()


class LocalLaserScannerGui(GUIBase):
    """ FIXME: Please document
    """
    # declare connectors
    locallaserscannerlogic = Connector(interface='LocalLaserScannerlogic')

    sigStart = QtCore.Signal()
    sigStop = QtCore.Signal()


    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self.log.debug('The following configuration was found.')

        # checking for the right configuration
        for key in config.keys():
            self.log.info('{0}: {1}'.format(key,config[key]))

    def on_activate(self):
        """ Definition and initialisation of the GUI.
        """
        self._local_laser_scanner_logic = self.locallaserscannerlogic()

        #####################
        # Configuring the dock widgets
        # Use the inherited class 'CounterMainWindow' to create the GUI window
        self._mw = LocalLaserScannerMainWindow()

        # Setup dock widgets
        # self._mw.centralwidget.hide()
        self._mw.setDockNestingEnabled(True)

        # Parameter display


        self._mw.start_f.setText('{0}'.format(self._local_laser_scanner_logic._start_f))
        self._mw.stop_f.setText('{0}'.format(self._local_laser_scanner_logic._stop_f))
        self._mw.cursorposition.setText('{0}'.format(int(self._local_laser_scanner_logic.frequency_range[0])))
        self._mw.refbinnum.setText('{0}'.format(self._local_laser_scanner_logic.ref_binnum))
        self._mw.noofbins.setText('{0}'.format(int(self._local_laser_scanner_logic.no_of_bins)))
        self._mw.scantime.setText('{0}'.format(self._local_laser_scanner_logic.scan_time))
        self._mw.timeperpoints.setText('{0}'.format(self._local_laser_scanner_logic.time_per_points))
        self._mw.returnspeed.setText('{0}'.format(self._local_laser_scanner_logic.return_speed))
        self._mw.noofloops.setText('{0}'.format(self._local_laser_scanner_logic.no_of_loops))

        # Plot labels.
        self._pw = self._mw.trace_PlotWidget
        self._pw2 = self._mw.trace_PlotWidget_2
        self._pw3 = self._mw.trace_PlotWidget_3

        plot_x_zeros = np.zeros(self._local_laser_scanner_logic.no_of_bins + 1)
        self._image = pg.ImageItem(image = np.array([plot_x_zeros]), axisOrder='row-major')
        #self.xax = self._pw.getAxis('bottom')

        self.plot2 = self._pw2.plotItem
        self.plot2.setLabel('left', 'Amplitude', color='#00ff00')
        self.plot2.setLabel('bottom', 'Frequency')
        self.plot2.showAxis('top', show = True)
        self.plot2.showAxis('right', show = True)
        self.plot2.setMouseEnabled(x = False, y = False)


        self.plot3 = self._pw3.plotItem
        self.plot3.setLabel('left', 'Amplitude', color='#00ff00')
        self.plot3.setLabel('bottom', 'Frequency')
        self.plot3.showAxis('top', show = True)
        self.plot3.showAxis('right', show = True)
        self.plot3.setMouseEnabled(x = False, y = False)


        self.region_cursor = pg.LinearRegionItem([int(self._mw.start_f.text()), int(self._mw.stop_f.text())], swapMode='block')
        self.region_cursor.setBounds([int(self._mw.start_f.text()), int(self._mw.stop_f.text())])
        self.main_cursor = pg.InfiniteLine(pos = self._local_laser_scanner_logic._main_cursor_position, angle = 90, movable = True, bounds = [int(self._mw.start_f.text()), int(self._mw.stop_f.text())])


        
        self._curve1 = pg.PlotDataItem(pen=pg.mkPen(palette.c1),#, style=QtCore.Qt.DotLine),
                                       symbol=None
                                       #symbol='o',
                                       #symbolPen=palette.c1,
                                       #symbolBrush=palette.c1,
                                       #symbolSize=3
                                       )
        self._curve2 = pg.PlotDataItem(pen=pg.mkPen(palette.c1),#, style=QtCore.Qt.DotLine),
                                       symbol=None
                                       #symbol='o',
                                       #symbolPen=palette.c1,
                                       #symbolBrush=palette.c1,
                                       #symbolSize=3
                                       )
        self._pw.addItem(self._image)
        self.plot2.addItem(self._curve1)
        self.plot3.addItem(self._curve2)





        # make correct button state
        self._mw.action_start.setChecked(False)
        self._initialize_plots()


        #####################
        # Connecting user interactions
        self._mw.action_start.triggered.connect(self.start_clicked)
        self._mw.action_save.triggered.connect(self.save_clicked)

        #####################
        # starting the physical measurement
        self.sigStart.connect(self.switchToScanLoop)
        self.sigStop.connect(self._local_laser_scanner_logic.stopMeasure)

        self._local_laser_scanner_logic.sigUpdatePlots.connect(self.updatePlots)
        self._local_laser_scanner_logic.sigSwitchToCursorLoop.connect(self.switchToCursorLoop, QtCore.Qt.QueuedConnection)

        ######################
        self.region_cursor.sigRegionChanged.connect(self.updateSweepRange)
        self.main_cursor.sigPositionChanged.connect(self.updateCursorPosition)
        self._mw.start_f.returnPressed.connect(self.setRegionCursorPosition)
        self._mw.stop_f.returnPressed.connect(self.setRegionCursorPosition)
        self._mw.cursorposition.returnPressed.connect(self.setCursorPosition)
        self._mw.noofbins.returnPressed.connect(self.setNoOfBins)
        self._mw.scantime.returnPressed.connect(self.setScanTime)
        self._mw.timeperpoints.returnPressed.connect(self.setTimePerPoints)
        self._mw.returnspeed.returnPressed.connect(self.setReturnSpeed)
        self._mw.noofloops.returnPressed.connect(self.setNoOfLoops)
        self._mw.resetpb.clicked.connect(self.resetSweepRange)
        self._mw.setbinnumpb.clicked.connect(self.setBinNum)


        ######################
        self._local_laser_scanner_logic.sigSwitchToCursorLoop.emit()

    def show(self):
        """Make window visible and put it above all other windows.
        """
        QtWidgets.QMainWindow.show(self._mw)
        self._mw.activateWindow()
        self._mw.raise_()

    def on_deactivate(self):
        """ Deactivate the module properly.
        """
        # Disconnect signals
        self.region_cursor.sigRegionChanged.disconnect()
        self.main_cursor.sigPositionChanged.disconnect()
        self._mw.start_f.returnPressed.disconnect()
        self._mw.stop_f.returnPressed.disconnect()
        self._mw.cursorposition.returnPressed.disconnect()
        self._mw.action_start.triggered.disconnect()
        self._mw.action_save.triggered.disconnect()

        

        self._mw.close()
        return 0
    
    def switchToCursorLoop(self):
        # initialize the current position
        self.moveToStartPosition()
        self.update_status(is_running = False)
        self._local_laser_scanner_logic.sigCursorLoopRepeat.emit()
       # if self._local_laser_scanner_logic.module_state() == 'locked':
        #    self._mw.action_start.setText('Stop')
        #else:
         #   self._mw.action_start.setText('Start')
    
    def switchToScanLoop(self):
        self._initialize_plots()
        self._local_laser_scanner_logic.stopCursorLoopRequest = True
        self.update_status(is_running = True)
        self._local_laser_scanner_logic._scan_loop_cnts = 0
        self._local_laser_scanner_logic.start_scan_loop()





    def updatePlots(self):
        """ The function that grabs the data and sends it to the plot.
        """
        self._image.setImage(image = np.array(self._local_laser_scanner_logic.plot_y_sum))
        self._curve1.setData(self._local_laser_scanner_logic.plot_x, self._local_laser_scanner_logic.plot_y_average)
        self._curve2.setData(self._local_laser_scanner_logic.plot_x, self._local_laser_scanner_logic.plot_y)

        if self._local_laser_scanner_logic.module_state() == 'locked':
            self._mw.action_start.setText('Stop')
        else:
            self._mw.action_start.setText('Start')

    def start_clicked(self):
        """ Handling the Start button to stop and restart the counter.
        """
        if self._local_laser_scanner_logic.module_state() == 'locked':
            #self._mw.action_start.setText('Start')
            self.sigStop.emit()
        else:
            #self._mw.action_start.setText('Stop')
            self.sigStart.emit()

    def save_clicked(self):
        """ Handling the save button to save the data into a file.
        """
        return
    


    def updateCursorPosition(self):
        """ Update the display of cursor position
        """
        self._local_laser_scanner_logic._main_cursor_position = int(self.main_cursor.value())
        self._mw.cursorposition.setText('{0}'.format(self._local_laser_scanner_logic._main_cursor_position))
    
    def updateSweepRange(self):
        """ Update the display of region cursor position
        """
        time.sleep(0.01)
        self._local_laser_scanner_logic._start_f = int(self.region_cursor.getRegion()[0])
        self._local_laser_scanner_logic._stop_f = int(self.region_cursor.getRegion()[1])
        self._local_laser_scanner_logic.ref_binnum = int((self._local_laser_scanner_logic._stop_f - self._local_laser_scanner_logic._start_f) / self._local_laser_scanner_logic.MHz_unit)
        self._mw.start_f.setText('{0}'.format(self._local_laser_scanner_logic._start_f))
        self._mw.stop_f.setText('{0}'.format(self._local_laser_scanner_logic._stop_f))
        self._mw.refbinnum.setText('{0}'.format(self._local_laser_scanner_logic.ref_binnum))





    def setRegionCursorPosition(self):
        self._local_laser_scanner_logic._start_f = int(self._mw.start_f.text())
        self._local_laser_scanner_logic._stop_f = int(self._mw.stop_f.text())
        sweeprange = [self._local_laser_scanner_logic._start_f,self._local_laser_scanner_logic._stop_f]
        self.region_cursor.setRegion(sweeprange)
        self._local_laser_scanner_logic.ref_binnum = int((self._local_laser_scanner_logic._stop_f - self._local_laser_scanner_logic._start_f) / self._local_laser_scanner_logic.MHz_unit)
        self._mw.refbinnum.setText('{0}'.format(self._local_laser_scanner_logic.ref_binnum))


    def resetSweepRange(self):
        self._local_laser_scanner_logic._start_f = int(self._local_laser_scanner_logic.frequency_range[0])
        self._local_laser_scanner_logic._stop_f = int(self._local_laser_scanner_logic.frequency_range[1])
        sweeprange = [self._local_laser_scanner_logic._start_f,self._local_laser_scanner_logic._stop_f]
        self.region_cursor.setRegion(sweeprange)
        self._local_laser_scanner_logic.ref_binnum = int((self._local_laser_scanner_logic._stop_f - self._local_laser_scanner_logic._start_f) / self._local_laser_scanner_logic.MHz_unit)
        self._mw.refbinnum.setText('{0}'.format(self._local_laser_scanner_logic.ref_binnum))
        self._mw.noofbins.setText('{0}'.format(self._local_laser_scanner_logic.ref_binnum))
        self.setNoOfBins()

    def update_status(self, is_running):

        # Block signals from firing
        self._mw.action_start.blockSignals(True)
        self._mw.action_resume.blockSignals(True)
        if is_running:
            self.plot2.removeItem(self.region_cursor)
            self.plot3.removeItem(self.main_cursor)
            self._mw.action_start.setText('Stop')
            
        else:
            self.plot2.addItem(self.region_cursor)
            self.plot3.addItem(self.main_cursor)
            self._mw.action_start.setText('Start')

        self._mw.action_start.blockSignals(False)
        self._mw.action_resume.blockSignals(False)

    def setCursorPosition(self):
        self.main_cursor.setValue(int(self._mw.cursorposition.text()))
    

    def setNoOfBins(self):
        self._local_laser_scanner_logic.no_of_bins = int(self._mw.noofbins.text())
        self._local_laser_scanner_logic.scan_time = float(self._local_laser_scanner_logic.no_of_bins * self._local_laser_scanner_logic.time_per_points)
        self._mw.scantime.setText('{0}'.format(self._local_laser_scanner_logic.scan_time))

    def setBinNum(self):
        self._mw.noofbins.setText('{0}'.format(self._local_laser_scanner_logic.ref_binnum))
        self.setNoOfBins()

    def setScanTime(self):
        self._local_laser_scanner_logic.scan_time = float(self._mw.scantime.text())
        self._local_laser_scanner_logic.time_per_points = self._local_laser_scanner_logic.scan_time / self._local_laser_scanner_logic.no_of_bins
        self._local_laser_scanner_logic._scanner_clock_frequency = int(1/self._local_laser_scanner_logic.time_per_points)
        self._mw.timeperpoints.setText('{0}'.format(self._local_laser_scanner_logic.time_per_points))
        self._local_laser_scanner_logic.sigScannerClockFrequencyChanged.emit()

    def setTimePerPoints(self):
        self._local_laser_scanner_logic.time_per_points = float(self._mw.timeperpoints.text())
        self._local_laser_scanner_logic._scanner_clock_frequency = int(1/self._local_laser_scanner_logic.time_per_points)
        self._local_laser_scanner_logic.scan_time = float(self._local_laser_scanner_logic.no_of_bins * self._local_laser_scanner_logic.time_per_points)
        self._mw.scantime.setText('{0}'.format(self._local_laser_scanner_logic.scan_time))
        self._local_laser_scanner_logic.sigScannerClockFrequencyChanged.emit()

    def setReturnSpeed(self):
        self._local_laser_scanner_logic.return_speed = float(self._mw.returnspeed.text())

    def setNoOfLoops(self):
        self._local_laser_scanner_logic.no_of_loops = int(self._mw.noofloops.text())

    def _initialize_plots(self):
        self._local_laser_scanner_logic.plot_x = np.linspace(self._local_laser_scanner_logic._start_f, self._local_laser_scanner_logic._stop_f, self._local_laser_scanner_logic.no_of_bins + 1)
        self._local_laser_scanner_logic.plot_y = []
        self._local_laser_scanner_logic.plot_y_average = []
        self._local_laser_scanner_logic.plot_y_sum = []
        self._local_laser_scanner_logic.return_x = np.linspace(self._local_laser_scanner_logic._stop_f, self._local_laser_scanner_logic._start_f, int(self._local_laser_scanner_logic.no_of_bins / self._local_laser_scanner_logic.return_speed) + 1)
        self.plot2.setXRange(self._local_laser_scanner_logic._start_f, self._local_laser_scanner_logic._stop_f)
        self.plot3.setXRange(self._local_laser_scanner_logic._start_f, self._local_laser_scanner_logic._stop_f)
        self.moveToStartPosition

    
    def moveToStartPosition(self):
        self._local_laser_scanner_logic.moveToPosition(self._local_laser_scanner_logic._start_f)
        self.main_cursor.setValue(self._local_laser_scanner_logic._start_f)
        self._local_laser_scanner_logic._main_cursor_position = int(self.main_cursor.value())
        self._mw.cursorposition.setText('{0}'.format(self._local_laser_scanner_logic._main_cursor_position))