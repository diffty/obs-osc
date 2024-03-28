import math
import asyncio

from pythonosc.osc_server import AsyncIOOSCUDPServer
from pythonosc.dispatcher import Dispatcher
from pythonosc.udp_client import SimpleUDPClient
import obspython

from collections import OrderedDict

import config
from comms import CommsManager

# GLOBALS
AUDIO_SOURCES = {}

def script_properties():
    properties = obspython.obs_properties_create()

    local_port_param = obspython.obs_properties_add_text(properties, "Local Port", "Local OSC device port", obspython.OBS_TEXT_DEFAULT)
    remote_ip_param = obspython.obs_properties_add_text(properties, "Remote IP", "Remote OSC device IP", obspython.OBS_TEXT_DEFAULT)
    remote_port_param = obspython.obs_properties_add_text(properties, "Remote Port", "Remote OSC device port", obspython.OBS_TEXT_DEFAULT)

    obspython.obs_property_set_visible(remote_ip_param, True)

    return properties


def script_defaults(settings):
    obspython.obs_data_set_default_int(settings, "local_port", config.LOCAL_PORT)
    obspython.obs_data_set_default_string(settings, "remote_ip", config.REMOTE_IP)
    obspython.obs_data_set_default_int(settings, "remote_port", config.REMOTE_PORT)


def script_update(settings):
    config.LOCAL_PORT = obspython.obs_data_get_default_int(settings, "local_port")
    config.REMOTE_IP = obspython.obs_data_get_default_string(settings, "remote_ip")
    config.REMOTE_PORT = obspython.obs_data_get_default_int(settings, "remote_port")


def get_audio_sources_from_scene(scene, source_dict=None):
    if source_dict is None:
        source_dict = OrderedDict()

    for sceneitem in obspython.obs_scene_enum_items(obspython.obs_scene_from_source(scene)):
        item_source = obspython.obs_sceneitem_get_source(sceneitem)
        name = obspython.obs_source_get_name(item_source)

        if obspython.obs_source_get_output_flags(item_source) & obspython.OBS_SOURCE_COMPOSITE:
            source_dict = get_audio_sources_from_scene(item_source, source_dict)
        
        if obspython.obs_source_get_output_flags(item_source) & obspython.OBS_SOURCE_AUDIO:
            source_active = obspython.obs_source_active(item_source)
            audio_active = obspython.obs_source_audio_active(item_source)
            priv_settings = obspython.obs_source_get_private_settings(item_source);
            hidden = obspython.obs_data_get_bool(priv_settings, "mixer_hidden");
            if not source_active or not audio_active or hidden:
                continue

            source_dict[name] = item_source

    return source_dict

def refresh_scenes():
    for i, scene_source in enumerate(obspython.obs_frontend_get_scenes()):
        scene_name = obspython.obs_source_get_name(scene_source)
        comms_manager.client.send_message(f"/obs/scene/label/num/{i+1}", scene_name)

def refresh_audio_faders():
    global AUDIO_SOURCES

    curr_scn_src = obspython.obs_frontend_get_current_scene()
    AUDIO_SOURCES = get_audio_sources_from_scene(curr_scn_src)

    # Hide all the sliders
    for i in range(10):
        comms_manager.client.send_message(f"/obs/audio/label/num/{i+1}/visible", False)
        comms_manager.client.send_message(f"/obs/audio/fader/num/{i+1}/visible", False)
        comms_manager.client.send_message(f"/obs/audio/monitoring/num/{i+1}/visible", False)

    # Show the necessary amount of slider & set their label & volume according to the sources
    for i, src_item in enumerate(AUDIO_SOURCES.items()):
        src_name, src_obj = src_item
        src_volume = obspython.obs_source_get_volume(src_obj)
        src_monitoring = obspython.obs_source_get_monitoring_type(src_obj)
        comms_manager.client.send_message(f"/obs/audio/label/num/{i+1}/visible", True)
        comms_manager.client.send_message(f"/obs/audio/label/num/{i+1}", src_name)
        comms_manager.client.send_message(f"/obs/audio/fader/num/{i+1}/visible", True)
        comms_manager.client.send_message(f"/obs/audio/fader/num/{i+1}", src_volume ** (1. / 3))
        comms_manager.client.send_message(f"/obs/audio/monitoring/num/{i+1}/visible", True)
        comms_manager.client.send_message(f"/obs/audio/monitoring/num/{i+1}", src_monitoring)


# +======== OBS CALLBACKS ========+
def on_source_create_callback(calldata):
    refresh_scenes()
    refresh_audio_faders()

signal_handler = obspython.obs_get_signal_handler()
obspython.signal_handler_connect(signal_handler, "source_create", on_source_create_callback)


# +======== OSC HANDLERS ========+
def scene_handler(address, *args):
    print(f"{address}: {args}")
    control, id_type, i_str = address.split("/")[3:6]

    if control == "button":
        i = int(i_str)-1
        scn = obspython.obs_frontend_get_scenes()[i]
        obspython.obs_frontend_set_current_scene(scn)

def audio_handler(address, *args):
    global AUDIO_SOURCES
    #print(f"{address}: {args}")
    control, id_type, i_str = address.split("/")[3:6]

    if control == "fader":
        #for i, src_item in enumerate(AUDIO_SOURCES.items()):
        #    src_name, src_obj = src_item
        #    if i_str == str(i+1):
        src_obj = list(AUDIO_SOURCES.values())[int(i_str)-1]
        volume_percent = args[0]
        dB = volume_percent**3
        obspython.obs_source_set_volume(src_obj, dB)
        #break
    
    elif control == "monitoring":
        src_obj = list(AUDIO_SOURCES.values())[int(i_str)-1]
        monitor_type = args[0]
        obspython.obs_source_set_monitoring_type(src_obj, monitor_type)


def osc_handler(address, *args):
    control = address.split("/")[3]
    if control == "refresh":
        refresh_scenes()
        refresh_audio_faders()


dispatcher = Dispatcher()
dispatcher.map("/obs/scene/*", scene_handler)
dispatcher.map("/obs/audio/*", audio_handler)
dispatcher.map("/obs/osc/*", osc_handler)


# +======== ASYNC/THREADED EVENT LOOP ========+
loop = asyncio.get_event_loop()
loop.stop()

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

def ticker_loop(delta_time):
    loop.stop()
    loop.run_forever()
    return True

def script_tick(delta_time):
    ticker_loop(delta_time)


# Init communications manager
if CommsManager.instance:
    comms_manager = CommsManager.instance
else:
    comms_manager = CommsManager(config.LOCAL_IP,
                                config.LOCAL_PORT,
                                config.REMOTE_IP,
                                config.REMOTE_PORT)

comms_manager.create_client()
comms_manager.create_server(dispatcher)


# Finally refresh scenes
refresh_scenes()
refresh_audio_faders()
