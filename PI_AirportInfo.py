VERSION = "0.1"

# Python import
from XPLMDefs import *
from XPLMDisplay import *
from XPLMGraphics import *
from XPLMMenus import *
from XPLMNavigation import *
from XPLMDataAccess import *
from XPWidgets import *
from XPStandardWidgets import *
from XPLMUtilities import *

from metar import Metar

import logging
import os
import platform
import urllib
import shutil
import time
import sys
from argparse import ArgumentParser
from operator import attrgetter

FILE_INF = "cycle_info.txt"
FILE_AWY = "earth_awy.dat"
FILE_FIX = "earth_fix.dat"
FILE_NAV = "earth_nav.dat"

# menu
SHOW_AIRPORT = 1

# design
MARGIN_W = 30
MARGIN_H = 30
WINDOW_W = 350
WINDOW_H = 190

# some constants
XPDIRS = ["Aircraft", "Airfoils"]
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT_NAME = os.path.split(os.path.abspath(__file__))[1]

def pjoin(*args, **kwargs):
  return os.path.join(*args, **kwargs).replace(os.path.sep, '/')
# ----------------------------------------------------------------------------

# logger:
log_formatter = logging.Formatter(
	"[%(asctime)s] %(levelname)-7s:  %(message)s",
	"%H:%M:%S"
)
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
# log to console:
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
console_handler.setLevel(logging.INFO)
logger.addHandler(console_handler)

# log to file:
log_path = pjoin(SCRIPT_DIR, SCRIPT_NAME.replace(".py", ".log"))
# logging.basicConfig(filename=log_path,level=logging.DEBUG)
file_handler = logging.FileHandler(filename=log_path, mode='w')
file_handler.setFormatter(log_formatter)
# file_handler.setLevel(logging.DEBUG)
logger.addHandler(file_handler)
# -------------------------------------------------------------------------------

def is_env_ok():
	# Check, if we are in X-Plane's root dir:
	for d in XPDIRS:
		if not os.path.isdir(os.path.join(os.getcwd(), d)):
			logger.warning("The script needs to be stored and launched "
							"in X-Plane's installation (root) directory.")
			return False
	fmsplans_dir = os.path.join(os.getcwd(), "Output", "FMS plans")
	if not os.path.isdir(fmsplans_dir):
		logger.warning("Cannot find directory \"%s\" to store SID/ STAR files."
						% fmsplans_dir)
		return False

	# Check if GNS430 dir exists:
	gns_dir = os.path.join(os.getcwd(), "Custom Data", "GNS430")
	if not os.path.isdir(gns_dir):
		logger.warning("Cannot find directory \"%s\". "
						"X-Plane 10.30 or higher needs to be installed."
						% gns_dir)
		return False

	navdata_dir = os.path.join(gns_dir, "navdata")

	# Check if PROC dir exists:
	# proc = "PROC" if "WIN" in platform.platform().upper() else "Proc"
	proc_dirs = ("PROC", "Proc")
	for proc in proc_dirs:
		proc_dir = os.path.join(navdata_dir, proc)
		if os.path.isdir(proc_dir):
			break

	if not os.path.isdir(proc_dir):
		logger.warning(
			"Cannot find one of the sub directories %s. "
			"below the directory \"%s\". "
			"Navigation database including SID/ STAR procedures "
			"needs to be installed for GNS 430/530 (X-Plane 10.30+)."
			" Use NavDataPro to achieve that for instance." %
			(proc_dirs, navdata_dir))
		return False

	# Check if PROC dir exists:
	custom_data_dir = os.path.join(
		gns_dir,
		os.pardir,
	)

	# Check if "airports.txt" file exists:
	airports_files = ("airports.txt", "Airports.txt")
	for airports in airports_files:
		airports_file_path = os.path.join(navdata_dir, airports)
		if os.path.isfile(airports_file_path):
			break
	if not os.path.isfile(airports_file_path):
		logger.warning(
			"Cannot find one of the files %s "
			"in the directory \"%s\"." %
			(airports_files, navdata_dir))
		return False

	# Check if "earth_fix.dat" file exists:
	fixes_file_path = os.path.join(custom_data_dir, "earth_fix.dat")
	if not os.path.isfile(fixes_file_path):
		logger.warning("Cannot find file \"%s\"." % fixes_file_path)
		return False

	# Check if "earth_nav.dat" dir exists:
	navaids_file_path = os.path.join(custom_data_dir, "earth_nav.dat")
	if not os.path.isfile(navaids_file_path):
		logger.warning("Cannot find file \"%s\"." % navaids_file_path)
		return False
	directories = [
		proc_dir,
		fmsplans_dir,
		navaids_file_path,
		fixes_file_path,
		airports_file_path]
	return directories


class PythonInterface:

	def XPluginStart(self):

		is_env_ok()

		self.Name = "Aiport Info" + VERSION
		self.Sig =  "TheoEsenwein.Python.AiportInfo"
		self.Desc = "A plugin to get some Aiport information."
		self.AirportWindowCreated = False
		self.current_airport_icao = ""
		self.current_airport_name = ""
		self.current_airport_info = ""
		self.current_airport_metar = None
		
		self.AirportMenuCB = self.AMHandler
		self.mPluginItem = XPLMAppendMenuItem(XPLMFindPluginsMenu(), "Aiport Info", 0, 1)
		self.mMain = XPLMCreateMenu(self, "Airport Information", XPLMFindPluginsMenu(), self.mPluginItem, self.AirportMenuCB, 0)
		self.mToggleWindow = XPLMAppendMenuItem(self.mMain, 'Toggle Window', SHOW_AIRPORT, 1)

  		# Custom Command
		self.AWToggle = XPLMCreateCommand("Aiprotinfo/Window_toggle", "Toggle Airport Info")
		self.AWToggleHandlerCB = self.AWToggleHandler
		XPLMRegisterCommandHandler(self, self.AWToggle, self.AWToggleHandlerCB, 1, 0)
	  
		return self.Name, self.Sig, self.Desc

	def XPluginStop(self):
		if self.AirportWindowCreated:
			XPDestroyWidget(self, self.AirportWindow, 1)
			self.AirportWindowCreated = False
		pass
	
	def XPluginEnable(self):
		return 1

	def XPluginDisable(self):
		pass        

	def XPluginReceiveMessage(self, inFromWho, inMessage, inParam):
		pass

	def AMHandler(self, inMenuRef, inItemRef):
		if inItemRef == SHOW_AIRPORT:
			 self.CreateAirportWindow()		

	def AWHandler(self, inMessage, inWidget, inParam1, inParam2):
	
 		if inMessage == xpMessage_CloseButtonPushed:
			if self.AirportWindowCreated:
				XPHideWidget(self.AirportWindow)
			return 1

		# Handle all button pushes
		if inMessage == xpMsg_PushButtonPressed:
			if str(inParam1) == str(self.BtnSearch):
				self.set_selected_icao_name()
				return 1

		return 0

	def AWToggleHandler(self, inCommand, inPhase, inRefcon):
		# execute the command only on press
		if inPhase == 0:
			if not self.AirportWindowCreated:
				self.CreateAirportWindow()
			else:
				if not XPIsWidgetVisible(self.AirportWindow):
					XPShowWidget(self.AirportWindow)
				else:
					XPHideWidget(self.AirportWindow)
		return 0
				
	def CreateAirportWindow(self):
  		if self.AirportWindowCreated:
			XPDestroyWidget(self, self.AirportWindow, 1)
		
		self.AirportWindowCreated = True

		Buffer = "Airport Info " + VERSION
		screen_w, screen_h = [], []
		XPLMGetScreenSize(screen_w, screen_h)
		left_window = int(screen_w[0]) - WINDOW_W - MARGIN_W
		top_window = int(screen_h[0]) - MARGIN_H
		right_window = left_window + WINDOW_W
		bottom_window = top_window - WINDOW_H

		row_h = 20
		row_h2 = 15
		padding = 5

		left_col_1 = left_window + padding
		right_col_1 = left_col_1 + 50
		left_col_2 = right_col_1 + padding
		right_col_2 = left_col_2 + 50
		left_col_3 = right_col_2 + padding
		right_col_3 = left_col_3 + 50

		left_half_window = left_window + WINDOW_W / 2


		# Create Window
		self.AirportWindow = XPCreateWidget(left_window, top_window, right_window, bottom_window, 1, Buffer, 1,  0, xpWidgetClass_MainWindow)
 		XPSetWidgetProperty(self.AirportWindow, xpProperty_MainWindowHasCloseBoxes, 1)

		# Icao entry
		top_row = top_window - 22
		self.AirportIcaoLb1 = XPCreateWidget(left_col_1, top_row, right_col_1, top_row - row_h, 1, "ICAO", 0, self.AirportWindow, xpWidgetClass_Caption)
		self.AirportIcao = XPCreateWidget(left_col_2, top_row, right_col_2 , top_row - row_h, 1, "", 0, self.AirportWindow, xpWidgetClass_TextField)
	   	self.BtnSearch = XPCreateWidget(left_col_3, top_row, right_col_3, top_row - row_h, 1, "Search", 0, self.AirportWindow, xpWidgetClass_Button)
		XPSetWidgetDescriptor(self.AirportIcao, str(self.current_airport_icao))

		# Show Result		
		top_row -= row_h
		self.InfoTitle = XPCreateWidget(left_col_1, top_row,right_col_3, top_row - row_h, 1, "Current Information", 0, self.AirportWindow, xpWidgetClass_Caption)
		top_row -= row_h
		self.InfoRow1 = XPCreateWidget(left_col_1, top_row,right_col_3, top_row - row_h, 1, "Airport:", 0, self.AirportWindow, xpWidgetClass_Caption)
		top_row -= row_h2
		self.InfoRow2 = XPCreateWidget(left_col_1, top_row,right_col_3, top_row - row_h2, 1, "QNH:", 0, self.AirportWindow, xpWidgetClass_Caption)
		top_row -= row_h2
		self.InfoRow3 = XPCreateWidget(left_col_1, top_row,right_col_3, top_row - row_h2, 1, "WIND:", 0, self.AirportWindow, xpWidgetClass_Caption)


		# Register the widget handler
		self.AMHandlerCB = self.AWHandler
		XPAddWidgetCallback(self, self.AirportWindow, self.AMHandlerCB)
		
		# Lets get some data
		self.init_data()

	def init_data(self):
		# Set the Input Box
		Route_Finder = Route()
		nearest_icao, nearest_name = Route_Finder.aiportinfo_by_nearest()
		if(nearest_name):
			XPSetWidgetDescriptor(self.AirportIcao, nearest_icao)
		
	def set_selected_icao_name(self):	
		# get the formfield
		Route_Finder = Route()
		out_icao_name = []

		XPGetWidgetDescriptor(self.AirportIcao, out_icao_name, 20)
		self.current_airport_icao = out_icao_name[0]
		
		# search for the information
		if(len(self.current_airport_icao) < 4):
			this_airporticao, this_airportname = Route_Finder.aiportinfo_by_nearest()		
		else:
			this_airporticao, this_airportname = Route_Finder.aiportinfo_by_icao(self.current_airport_icao)		
	
		self.current_airport_icao = this_airporticao
		self.current_airport_name = this_airportname

		self.current_airport_metar = Route_Finder.get_airportweather_icao(self.current_airport_icao)

		self.print_airport_info()

	def print_airport_info(self):
		XPSetWidgetDescriptor(self.InfoRow1, "Airport: " +  str(self.current_airport_name) + "(" + str(self.current_airport_icao) + ")")

		if(self.current_airport_metar):
			XPSetWidgetDescriptor(self.InfoRow2, "QNH: " +  str(self.current_airport_metar.press))
			XPSetWidgetDescriptor(self.InfoRow3, "WIND: " + str(self.current_airport_metar.wind_dir) + "/" +  str(self.current_airport_metar.wind_speed))			

class Route(object):

	def call_lan_lot(self):
		
		lat = [XPLMGetDataf(XPLMFindDataRef("sim/flightmodel/position/latitude"))]
		lon = [XPLMGetDataf(XPLMFindDataRef("sim/flightmodel/position/longitude"))]

		return lat, lon

	def airportidname_by_ref(self, ref):

		id = []
		name = []

		aiport = XPLMGetNavAidInfo(ref, None, None, None, None, None, None, id, name, None)

		return id, name

	def airportlatlon_by_ref(self, ref):

		lat = []
		lon = []

		aiport = XPLMGetNavAidInfo(ref, None, lat, lon, None, None, None, None, None, None)

		return lon, lat

	def airportinfo_by_local(self):

		current_lat, current_lon = Route.call_lan_lot(self)

		id = []
		name = []
		ref = XPLMFindNavAid(None, None, current_lat[0], current_lon[0], None, xplm_Nav_Airport)

		id, airport_names = self.airportidname_by_ref(ref)

		if(len(airport_names) > 0):
			return id[0], airport_names[0]
		else:
			return None

	def aiportlatlon_by_icao(self, icao):
		
		ref = XPLMFindNavAid(None, icao, None, None, None, xplm_Nav_Airport)
		airport_lat, airport_lon  = self.airportlatlon_by_ref(ref)

		return airport_lat[0], airport_lon[0]

	def aiportinfo_by_icao(self, name):

		current_lat, current_lon = Route.call_lan_lot(self)
		ref = XPLMFindNavAid(None, name, None, None, None, xplm_Nav_Airport)

		id, airport_names = self.airportidname_by_ref(ref)

		if(len(airport_names) > 0):
			return id[0], airport_names[0]
		else:
			return None

	def aiportinfo_by_nearest(self):
		
		airport_ids, airport_names  = Route.airportinfo_by_local(self)		

		if(len(airport_ids) > 0):
			return airport_ids, airport_names
		else:
			return None

	def get_airportweather_icao(self, icao):
		AWWeather = Weather(icao)
		return AWWeather.data
		
		
class Weather(object):

	def __init__(self, icao):

		self.icao = icao
		self.metarcode = None
		self.observations = None
		self.data = None

		self.get_noaa_weather()
		self.convert_meta()

	def get_noaa_weather(self):
		
		link = "http://tgftp.nws.noaa.gov/data/observations/metar/stations/" + self.icao.upper() + ".TXT"

		f = urllib.urlopen(link)

		if(f.getcode() != 404):
			self.metarcode = f.readlines()[1]
			

	def convert_meta(self):

		if(self.metarcode):
			self.data = Metar.Metar(self.metarcode)


		