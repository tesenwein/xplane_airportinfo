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
WINDOW_W = 400
WINDOW_H = 300

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
console_handler = logging.Stream_handler()
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

		self.Name = "Aiport Info" + VERSION
		self.Sig =  "TheoEsenwein.Python.AiportInfo"
		self.Desc = "A plugin to get some Aiport information."
		self.airport_window_created = False
		self.current_airport_icao = ""
		self.current_airport_name = ""
		self.current_airport_metar = None
		self.current_airport_runways = None
		self.current_aiprot_openrunway = None

		self.airpot_rwy_widget_container = None
		
		self.airport_menu_cb = self.am_handler
		self.menu_plugin_item = XPLMAppendMenuItem(XPLMFindPluginsMenu(), "Aiport Info", 0, 1)
		self.menu_main = XPLMCreateMenu(self, "Airport Information", XPLMFindPluginsMenu(), self.menu_plugin_item, self.airport_menu_cb, 0)
		self.menu_toggle_window = XPLMAppendMenuItem(self.menu_main, 'Toggle Window', SHOW_AIRPORT, 1)

  		# Custom Command
		self.aw_toggle = XPLMCreateCommand("Aiprotinfo/Window_toggle", "Toggle Airport Info")
		self.aw_toggle_handler_cb = self.aw_toggleHandler
		XPLMRegisterCommandHandler(self, self.aw_toggle, self.aw_toggle_handler_cb, 1, 0)
	  
		return self.Name, self.Sig, self.Desc

	def XPluginStop(self):
		if self.airport_window_created:
			XPDestroyWidget(self, self.airport_window, 1)
			self.airport_window_created = False
		pass
	
	def XPluginEnable(self):
		return 1

	def XPluginDisable(self):
		pass        

	def XPluginReceiveMessage(self, inFromWho, inMessage, inParam):
		pass

	def am_handler(self, inMenuRef, inItemRef):
		if inItemRef == SHOW_AIRPORT:
			 self.create_airport_window()		

	def aw_handler(self, inMessage, inWidget, inParam1, inParam2):
	
 		if inMessage == xpMessage_CloseButtonPushed:
			if self.airport_window_created:
				XPHideWidget(self.airport_window)
			return 1

		# Handle all button pushes
		if inMessage == xpMsg_PushButtonPressed:
			if str(inParam1) == str(self.BtnSearch):
				self.set_selected_icao_name()
				return 1

		return 0

	def aw_toggleHandler(self, inCommand, inPhase, inRefcon):
		# execute the command only on press
		if inPhase == 0:
			if not self.airport_window_created:
				self.create_airport_window()
			else:
				if not XPIsWidgetVisible(self.airport_window):
					XPShowWidget(self.airport_window)
				else:
					XPHideWidget(self.airport_window)
		return 0
				
	def create_airport_window(self):
  		if self.airport_window_created:
			XPDestroyWidget(self, self.airport_window, 1)
		
		self.airport_window_created = True

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
		self.airport_window = XPCreateWidget(left_window, top_window, right_window, bottom_window, 1, Buffer, 1,  0, xpWidgetClass_MainWindow)
 		XPSetWidgetProperty(self.airport_window, xpProperty_MainWindowHasCloseBoxes, 1)

		# Icao entry
		top_row = top_window - 22
		self.AirportIcaoLb1 = XPCreateWidget(left_col_1, top_row, right_col_1, top_row - row_h, 1, "ICAO", 0, self.airport_window, xpWidgetClass_Caption)
		self.AirportIcao = XPCreateWidget(left_col_2, top_row, right_col_2 , top_row - row_h, 1, "", 0, self.airport_window, xpWidgetClass_TextField)
	   	self.BtnSearch = XPCreateWidget(left_col_3, top_row, right_col_3, top_row - row_h, 1, "Search", 0, self.airport_window, xpWidgetClass_Button)
		XPSetWidgetDescriptor(self.AirportIcao, str(self.current_airport_icao))

		# Show Result		
		top_row -= row_h2
		self.info_row_1 = XPCreateWidget(left_col_1, top_row, right_col_3, top_row - row_h, 1, "", 0, self.airport_window, xpWidgetClass_Caption)
		top_row -= row_h2
		self.info_row_2 = XPCreateWidget(left_col_1, top_row, right_col_3, top_row - row_h2, 1, "", 0, self.airport_window, xpWidgetClass_Caption)
		top_row -= row_h2
		self.info_row_3 = XPCreateWidget(left_col_1, top_row, right_col_3, top_row - row_h2, 1, "", 0, self.airport_window, xpWidgetClass_Caption)
		top_row -= row_h2
		self.info_row_4 = XPCreateWidget(left_col_1, top_row, right_col_3, top_row - row_h2, 1, "", 0, self.airport_window, xpWidgetClass_Caption)
		top_row -= row_h2
		self.info_row_5 = XPCreateWidget(left_col_1, top_row, right_col_3, top_row - row_h2, 1, "", 0, self.airport_window, xpWidgetClass_Caption)
		
		top_row -= row_h
		self.rnwy_info = XPCreateWidget(left_col_1, top_row, right_window-padding, bottom_window+padding, 1, "" ,  0,self.airport_window, xpWidgetClass_SubWindow)
		XPSetWidgetProperty(self.rnwy_info, xpProperty_SubWindowType, xpSubWindowStyle_SubWindow)

 		# Init the Container
		self.airpot_rwy_widget_container = XPWidgetContainer(self.airport_window, left_col_1, right_col_3, top_row+row_h2, row_h2)

		# Register the widget handler
		self.am_handlerCB = self.aw_handler
		XPAddWidgetCallback(self, self.airport_window, self.am_handlerCB)
		
		# Lets get some data
		self.init_data()

	def init_data(self):
		# Set the Input Box
		Route_Finder = Route()
		nearest_icao, nearest_name = Route_Finder.aiportinfo_by_nearest()
		if(nearest_name):
			XPSetWidgetDescriptor(self.AirportIcao, nearest_icao)

	def print_airport_info(self):
    		
		self.airpot_rwy_widget_container.remove_all()

		XPSetWidgetDescriptor(self.info_row_1, "Airport: " +  str(self.current_airport_name) + " (" + str(self.current_airport_icao) + ")")

		if(self.current_airport_metar):
			XPSetWidgetDescriptor(self.info_row_2, "Qnh: {} / {}".format(self.current_airport_metar.press.string("mb"),self.current_airport_metar.press.string("in")))
			XPSetWidgetDescriptor(self.info_row_3, "Wind: " + str(self.current_airport_metar.wind_dir) + " / " + self.current_airport_metar.wind())			
			XPSetWidgetDescriptor(self.info_row_4, "Visiblilty: " + self.current_airport_metar.visibility())			
			XPSetWidgetDescriptor(self.info_row_5, "Weather: " + self.current_airport_metar.sky_conditions())			
		


		# Get all Runways
		if(self.current_airport_runways):
			runway_strresult = ""
			for runway_info in self.current_airport_runways:	
				prefix = ""
				if(self.get_runway_info(runway_info).id == self.current_aiprot_openrunway.id):
					prefix = "*"

				runway_strresult = prefix + self.get_runway_str(self.get_runway_info(runway_info)) + "\n"									

				self.airpot_rwy_widget_container.new_caption(runway_strresult)

			#XPSetWidgetDescriptor(self.rnwyInfoContent, runway_strresult)


	def set_selected_icao_name(self):	
		# get the formfield
		Route_Finder = Route()
		out_icao_name = []

		XPGetWidgetDescriptor(self.AirportIcao, out_icao_name, 20)
		self.current_airport_icao = out_icao_name[0].upper()

		#self.current_airport_icao = "LSZH"
		
		# search for the information
		if(len(self.current_airport_icao) < 4):
			this_airporticao, this_airportname = Route_Finder.aiportinfo_by_nearest()		
		else:
			this_airporticao, this_airportname = Route_Finder.aiportinfo_by_icao(self.current_airport_icao)		
	
		self.current_airport_icao = this_airporticao
		self.current_airport_name = this_airportname

		self.current_airport_metar = Route_Finder.airport_weather_by_icao(self.current_airport_icao)

		AirportOb = Airport(self.current_airport_icao)
		self.current_airport_runways = AirportOb.runways

		if(self.current_airport_metar and self.current_airport_metar.wind_dir):
			self.current_aiprot_openrunway = AirportOb.open_runway(self.current_airport_metar.wind_dir.value())

		self.print_airport_info()

	def get_runway_info(self, runway_id):
		return self.current_airport_runways[str(runway_id)]

	

		self.airpot_rwy_widget_container.remove_all()

		XPSetWidgetDescriptor(self.info_row_1, "Airport: " +  str(self.current_airport_name) + " (" + str(self.current_airport_icao) + ")")

		if(self.current_airport_metar):
			XPSetWidgetDescriptor(self.info_row_2, "Qnh: {} / {}".format(self.current_airport_metar.press.string("mb"),self.current_airport_metar.press.string("in")))
			XPSetWidgetDescriptor(self.info_row_3, "Wind: " + str(self.current_airport_metar.wind_dir) + " / " + self.current_airport_metar.wind())			
			XPSetWidgetDescriptor(self.info_row_4, "Visiblilty: " + self.current_airport_metar.visibility())			
			XPSetWidgetDescriptor(self.info_row_5, "Weather: " + self.current_airport_metar.sky_conditions())			
		


		# Get all Runways
		if(self.current_airport_runways):
			runway_strresult = ""
			for runway_info in self.current_airport_runways:	
				prefix = ""
				if(self.get_runway_info(runway_info).id == self.current_aiprot_openrunway.id):
					prefix = "*"

				runway_strresult = prefix + self.get_runway_str(self.get_runway_info(runway_info)) + "\n"									

				self.airpot_rwy_widget_container.new_caption(runway_strresult)

			#XPSetWidgetDescriptor(self.rnwyInfoContent, runway_strresult)
				
	def get_runway_str(self, runway):
			
		if(runway.ils != "0.000"):
			return "Rwy: {}({}) ILS: {}({}) FT: {}".format(runway.id, 
															runway.hdg,
															runway.ils,
															runway.ilscrs,
															runway.length)
		else:
			return "Rwy: {}({}) FT: {}".format(runway.id, 
												runway.hdg,
												runway.length)
		return None
			
class XPWidgetContainer(object):
	
	def __init__(self, parent_container, left, right, top, row_h = 13):
	   
		self.parent_container = parent_container
		self.container = []
		self.left = left
		self.right = right
		self.top = top
		self.current_top = top
		self.row_h = row_h

	def new_caption(self, str_cap):

		self.current_top -= self.row_hx
		widget = XPCreateWidget(self.left, self.current_top, self.right, self.current_top-self.row_h, 1, str_cap,  0, self.parent_container, xpWidgetClass_Caption)
		self.container.append(widget)	

	def remove_all(self):
		
		if(len(self.container)>0):
			for i in self.container:
				XPHideWidget(i)
				#XPDestroyWidget(i,self.parent_container, 0)

		# Reset the height
		self.current_top = self.top


class Route(object):

	def call_lan_lot(self):
		
		lat = [XPLMGetDataf(XPLMFindDataRef("sim/flightmodel/position/latitude"))]
		lon = [XPLMGetDataf(XPLMFindDataRef("sim/flightmodel/position/longitude"))]

		return lat, lon

	def airport_id_name_by_ref(self, ref):

		id = []
		name = []

		aiport = XPLMGetNavAidInfo(ref, None, None, None, None, None, None, id, name, None)

		return id, name

	def airport_latlon_by_ref(self, ref):

		lat = []
		lon = []

		aiport = XPLMGetNavAidInfo(ref, None, lat, lon, None, None, None, None, None, None)

		return lon, lat

	def airport_info_by_local(self):

		current_lat, current_lon = Route.call_lan_lot(self)

		id = []
		name = []
		ref = XPLMFindNavAid(None, None, current_lat[0], current_lon[0], None, xplm_Nav_Airport)

		id, airport_names = self.airport_id_name_by_ref(ref)

		if(len(airport_names) > 0):
			return id[0], airport_names[0]
		else:
			return None

	def aiport_latlon_by_icao(self, icao):
		
		ref = XPLMFindNavAid(None, icao, None, None, None, xplm_Nav_Airport)
		airport_lat, airport_lon  = self.airport_latlon_by_ref(ref)

		return airport_lat[0], airport_lon[0]

	def aiportinfo_by_icao(self, name):

		current_lat, current_lon = Route.call_lan_lot(self)
		ref = XPLMFindNavAid(None, name, None, None, None, xplm_Nav_Airport)

		id, airport_names = self.airport_id_name_by_ref(ref)

		if(len(airport_names) > 0):
			return id[0], airport_names[0]
		else:
			return None

	def aiportinfo_by_nearest(self):
		
		airport_ids, airport_names  = Route.airport_info_by_local(self)		

		if(len(airport_ids) > 0):
			return airport_ids, airport_names
		else:
			return None

	def airport_weather_by_icao(self, icao):
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

class Runway(object):
	
	def __init__(self, id, hdg, ils, ilscrs, length):

		self.id = id
		self.hdg = hdg
		self.ils = ils
		self.ilscrs = ilscrs
		self.length = length

class Airport(object):

	def __init__(self, icao_code):

		self.icao = icao_code
		self.directories = is_env_ok()
		self.airports_file_path = self.directories[4]
		self.runways = None

		self.read_runway_information()

	def read_runway_information(self):
		runways = {}
		with open(self.airports_file_path, 'r') as f:
			lines = f.readlines()
			is_needed_apt = False
			for no, line in enumerate(lines):
				if line.startswith("A,%s," % self.icao.upper()):
					is_needed_apt = True
					continue
				if is_needed_apt:
					if line.strip().replace('\r', '').replace('\n', ''):
						rwy_info = line.strip().split(',')
						rwy_id = rwy_info[1]
						rwy_hdg = rwy_info[2]
						rwy_length = rwy_info[3]
						rwy_ils = rwy_info[6]
						rwy_ilscrs = rwy_info[7]
						runways.update(
							{
								rwy_id: Runway(rwy_id,rwy_hdg,rwy_ils,rwy_ilscrs,rwy_length)
							}
						)
					else:
						break

		self.runways = runways

	def open_runway(self, wind):

		runways_simple = []

		for runway in self.runways:
			runways_simple.append(int(self.runways[runway].hdg))

		runway_dir = min(runways_simple, key=lambda x:abs(x-int(wind)))

		for runway in self.runways:
			if(int(self.runways[runway].hdg) == runway_dir):
				return self.runways[runway]

		return None
