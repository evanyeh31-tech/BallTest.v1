from vpython import *
import math
import time
from pythonosc import udp_client
from pythonosc import dispatcher
from pythonosc import osc_server
import threading
import random
import colorsys

# --- OSC Client Configuration (VPython -> REAPER) ---
# REAPER's IP address. Use "127.20.10.5" if REAPER and VPython are on the same computer.
# Otherwise, set it to the actual IP address of the computer where REAPER is running.
reaper_ip = "172.20.10.5"
# Define a single OSC port (for sending messages to REAPER)
osc_port = 8000

# Create a single OSC client
osc_client = udp_client.SimpleUDPClient(reaper_ip, osc_port)

# --- OSC Server Configuration (REAPER -> VPython) ---
# VPython's IP and port for listening as a server
# Note: This port must match the "Target Port" set in REAPER and must not conflict with
# the port VPython uses to send messages to REAPER.
# Use "127.0.0.1" if REAPER and VPython are on the same computer.
# Otherwise, set it to the actual IP address of the computer where VPython is running.
VPYTHON_SERVER_IP = "127.0.0.1"
VPYTHON_SERVER_PORT = 9002

# Global variables to store status received from REAPER
reaper_play_status = False
reaper_master_volume = 0.0
reaper_track_volumes = {} # Stores fader volumes for each track, e.g., {2: 0.5, 3: 0.8, 11: 0.7}

# Initialize track 11's volume to ensure it exists at startup
reaper_track_volumes[11] = 0.0

# Global light object to control scene brightness
master_light = None

# Ambisonics large sphere fade-out related variables
ambisonics_hemisphere_fade_active = False
ambisonics_hemisphere_fade_start_time = -1.0
ambisonics_hemisphere_fade_duration = 3.0 # Fade out time 3 seconds
ambisonics_hemisphere_initial_opacity = 0.0
ambisonics_hemisphere_initial_color = color.black

# New: Switch to control whether VPython sends track fader commands
vpython_control_faders_enabled = True # Initial setting is True (enabled)

# --- OSC Message Handling Functions (called by OSC server) ---
def handle_play_status(address, *args):
    """Handles messages for REAPER play status"""
    global reaper_play_status, ambisonics_hemisphere_fade_active, ambisonics_hemisphere_fade_start_time, \
           ambisonics_hemisphere_initial_opacity, ambisonics_hemisphere_initial_color
    if args and isinstance(args[0], (int, float)):
        new_play_status = bool(args[0])
        if new_play_status != reaper_play_status: # Only react if status changes
            reaper_play_status = new_play_status
            print(f"Received REAPER play status: {reaper_play_status}")

            if not reaper_play_status: # REAPER stops playing
                ambisonics_hemisphere_fade_active = True
                ambisonics_hemisphere_fade_start_time = time.time()
                ambisonics_hemisphere_initial_opacity = ambisonics_hemisphere.opacity
                ambisonics_hemisphere_initial_color = ambisonics_hemisphere.color
                # Stop other visual element movements
                for ball in inner_balls + inner_balls_2 + inner_balls_3 + inner_balls_4:
                    ball.vel = vector(0,0,0)
                    ball.angular_vel = vector(0,0,0)
                for ring_obj in ring_objects_list:
                    ring_obj.vel = vector(0,0,0)
                    ring_obj.angular_vel = vector(0,0,0)
            else: # REAPER starts playing
                ambisonics_hemisphere_fade_active = False # Stop any ongoing fade-out

def handle_master_volume(address, *args):
    """Handles REAPER master volume messages"""
    global reaper_master_volume, master_light # Include master_light
    if args and isinstance(args[0], (int, float)):
        reaper_master_volume = float(args[0])
        print(f"Received REAPER Master Volume: {reaper_master_volume:.2f}")
        # You can update VPython's visual effects here based on master volume
        # For example: adjust scene brightness or particle count based on master volume
        # Ensure master_light is accessed only after VPython scene initialization
        if master_light: # Check if master_light is initialized
             # Directly modify the color of the existing light source
             master_light.color = color.white * (0.5 + reaper_master_volume/2)

def handle_track_volume(address, *args):
    """Handles single track fader volume messages (e.g., /track/2/volume or /track/11/volume)"""
    global reaper_track_volumes
    try:
        # Parse track number from address
        parts = address.split('/')
        track_num = int(parts[2])
        if args and isinstance(args[0], (int, float)):
            volume_value = float(args[0])
            reaper_track_volumes[track_num] = volume_value

    except (ValueError, IndexError):
        print(f"Failed to parse track fader volume message address: {address}")


# --- Configure OSC Dispatcher ---
# Map OSC addresses to handler functions
dispatcher_instance = dispatcher.Dispatcher()
dispatcher_instance.map("/play", handle_play_status)
dispatcher_instance.map("/stop", handle_play_status)
dispatcher_instance.map("/master/volume", handle_master_volume)
dispatcher_instance.map("/track/*/volume", handle_track_volume)

# --- Create and Start OSC Server (in a separate thread) ---
def start_osc_server():
    server = osc_server.ThreadingOSCUDPServer(
        (VPYTHON_SERVER_IP, VPYTHON_SERVER_PORT), dispatcher_instance)
    print(f"VPython OSC Server listening on {VPYTHON_SERVER_IP}:{VPYTHON_SERVER_PORT}")
    server.serve_forever()

# Start the server thread before your VPython simulation begins
osc_server_thread = threading.Thread(target=start_osc_server)
osc_server_thread.daemon = True
osc_server_thread.start()


# Your existing VPython code starts here
# ----------------------------------------------------------------------------------------------------

# Track numbers (VPython will actively control the volume/position of these tracks and visualize them as Ambisonics spheres)
track_numbers = [2, 3, 4, 5, 6, 7, 8, 9, 10]
master_track_number = 1

max_volume = 0.7
decay_time = 1.5

pan_offset = 0.5

master_reverb_drywet_on = 0.8
master_reverb_drywet_off = 0.0

reverb_active_time = -1.0
reverb_full_wet_duration = 1.0
reverb_decay_duration = 1.0

# Azimuth and Elevation trigger cooldown time
azimuth_elevation_cooldown_time = 2.0

# Quadrant data (all rings share this data as they all control tracks 1-9)
quadrant_decay_timers = [-1] * len(track_numbers)
quadrant_volumes = [0.0] * len(track_numbers)
quadrant_pans = [0.5] * len(track_numbers)

quadrant_ball_stats = [{"count": 0, "total_speed": 0.0} for _ in range(len(track_numbers))]

# Azimuth related variables
quadrant_azimuths = [0.0] * len(track_numbers)
default_azimuth = 0.5
azimuth_decay_time = 5.0
quadrant_azimuth_last_trigger_time = [-1.0] * len(track_numbers)

# Elevation related variables
quadrant_elevations = [0.0] * len(track_numbers)
default_elevation = 0.5
elevation_decay_time = 5.0
quadrant_elevation_last_trigger_time = [-1.0] * len(track_numbers)

# For smooth volume decay on clear
clear_volume_decay_duration = 3.0
quadrant_volume_clearing = [False] * len(track_numbers)
quadrant_clear_start_time = [-1.0] * len(track_numbers)
quadrant_clear_initial_volume = [0.0] * len(track_numbers)

# For master reverb plugin control (ID 12)
master_fx_param_12_value = 0.0
master_fx_param_12_start_time = -1.0
master_fx_param_12_ramp_duration = 0.5
master_fx_param_12_decay_duration = 10.0
master_fx_param_12_state = "off"

# Ambisonics hemisphere related variables
ambisonics_hemisphere = None
# Map track_number to VPython sphere and label
projected_sound_sources = {}
projected_sound_labels = {}

hemisphere_radius = 10.0
hemisphere_center = vector(0, 5, 0)

# New constants for the range of spheres per track in Ambisonics view
MAX_SPHERES_PER_TRACK = 10
MIN_SPHERES_PER_TRACK = 3
# Sphere size
INDIVIDUAL_SOUND_SOURCE_RADIUS = 0.4


# OSC transmission optimization parameters
OSC_UPDATE_INTERVAL = 0.2
OSC_VALUE_THRESHOLD = 0.01

# Store last sent OSC values and times
last_sent_volume = [0.0] * len(track_numbers)
last_sent_azimuth = [0.0] * len(track_numbers)
last_sent_elevation = [0.0] * len(track_numbers)
last_sent_master_reverb_drywet = 0.0
last_sent_master_fx_param_12 = 0.0

last_volume_send_time = [0.0] * len(track_numbers)
last_azimuth_send_time = [0.0] * len(track_numbers)
last_elevation_send_time = [0.0] * len(track_numbers)
last_master_reverb_send_time = 0.0
last_master_fx_param_12_send_time = 0.0

# New: Ring mass (for simplified angular momentum) and ball attraction strength
ring_mass = 1.0 # Simplified ring mass for physics calculations

# Ball attraction related variables
SMALL_ATTRACTION_STRENGTH = 0.1
LARGE_ATTRACTION_STRENGTH = 8.0
ball_attraction_strength = SMALL_ATTRACTION_STRENGTH # Initial attraction strength is small
current_attraction_state = "small" # Initial state

def send_osc_message(address, value, current_time, last_sent_value_ref, last_send_time_ref):
    """
    Sends all OSC messages to a single port (8000).
    Adds threshold and time interval control to reduce message frequency.
    """
    global last_sent_master_reverb_drywet, last_sent_master_fx_param_12, last_master_reverb_send_time, last_master_fx_param_12_send_time, reaper_track_volumes, vpython_control_faders_enabled

    # Special handling for Master Reverb dry/wet
    if address == f"/track/{master_track_number}/reverb/drywet":
        if abs(value - last_sent_master_reverb_drywet) > OSC_VALUE_THRESHOLD or \
                current_time - last_master_reverb_send_time > OSC_UPDATE_INTERVAL or \
                (value == master_reverb_drywet_off and last_sent_master_reverb_drywet != master_reverb_drywet_off):
            try:
                osc_client.send_message(address, float(value))
                last_sent_master_reverb_drywet = value
                last_master_reverb_send_time = current_time
            except Exception as e:
                print(f"Error sending OSC message to {address} with value {value}: {e}")
        return

    # Special handling for Master FX Param 12
    if address == f"/track/{master_track_number}/fx/1/fxparam/12/value":
        if abs(value - last_sent_master_fx_param_12) > OSC_VALUE_THRESHOLD or \
                current_time - last_master_fx_param_12_send_time > OSC_UPDATE_INTERVAL or \
                (value == 0.0 and last_sent_master_fx_param_12 != 0.0):
            try:
                osc_client.send_message(address, float(value))
                last_sent_master_fx_param_12 = value
                last_master_fx_param_12_send_time = current_time
            except Exception as e:
                print(f"Error sending OSC message to {address} with value {value}: {e}")
        return

    # For other track parameters (Volume, Azimuth, Elevation)
    track_index = -1
    track_num_from_address = -1
    try:
        # Parse track number from address and find the corresponding index
        parts = address.split('/')
        track_num_from_address = int(parts[2])
        track_index = track_numbers.index(track_num_from_address)
    except (ValueError, IndexError):
        # If unable to parse or not in track_numbers, send directly (e.g., /marker messages)
        try:
            osc_client.send_message(address, float(value))
        except Exception as e:
            print(f"Error sending OSC message to {address} with value {value}: {e}")
        return

    # Update corresponding last_sent_value and last_send_time based on address type
    if "/volume" in address:
        # Only send volume commands when vpython_control_faders_enabled is True
        if vpython_control_faders_enabled:
            if abs(value - last_sent_value_ref[track_index]) > OSC_VALUE_THRESHOLD or \
                    current_time - last_send_time_ref[track_index] > OSC_UPDATE_INTERVAL or \
                    (value == 0.0 and last_sent_value_ref[track_index] != 0.0): # Ensure volume is sent when it goes to zero
                try:
                    osc_client.send_message(address, float(value))
                    last_sent_value_ref[track_index] = value
                    last_send_time_ref[track_index] = current_time
                    # Key modification: When VPython sends volume, immediately update local reaper_track_volumes
                    # This way, VPython's internal values will immediately reflect the sent volume, used for background brightness calculation
                    reaper_track_volumes[track_num_from_address] = value
                except Exception as e:
                    print(f"Error sending OSC message to {address} with value {value}: {e}")
        else:
            pass

    elif "/fx/2/fxparam/8/value" in address: # Azimuth
        if abs(value - last_sent_value_ref[track_index]) > OSC_VALUE_THRESHOLD or \
                current_time - last_send_time_ref[track_index] > OSC_UPDATE_INTERVAL:
            try:
                osc_client.send_message(address, float(value))
                last_sent_value_ref[track_index] = value
                last_send_time_ref[track_index] = current_time
            except Exception as e:
                print(f"Error sending OSC message to {address} with value {value}: {e}")
    elif "/fx/2/fxparam/9/value" in address: # Elevation
        if abs(value - last_sent_value_ref[track_index]) > OSC_VALUE_THRESHOLD or \
                current_time - last_send_time_ref[track_index] > OSC_UPDATE_INTERVAL:
            try:
                osc_client.send_message(address, float(value))
                last_sent_value_ref[track_index] = value
                last_send_time_ref[track_index] = current_time
            except Exception as e:
                print(f"Error sending OSC message to {address} with value {value}: {e}")
    else: # Other unoptimized OSC messages (e.g., /pan)
        try:
            osc_client.send_message(address, float(value))
        except Exception as e:
            print(f"Error sending OSC message to {address} with value {value}: {e}")


# Initialize volume, pan, Azimuth, and Elevation for all tracks
# Temporarily enable fader control to ensure initial volume commands are sent
original_fader_control_state = vpython_control_faders_enabled
vpython_control_faders_enabled = True

for i in range(len(track_numbers)): # Now initializing for tracks 2-10
    send_osc_message(f"/track/{track_numbers[i]}/volume", 0.0, time.time(), last_sent_volume, last_volume_send_time)
    # Pan messages are not optimized, send directly
    try:
        osc_client.send_message(f"/track/{track_numbers[i]}/pan", float(pan_offset))
    except Exception as e:
        print(f"Error sending OSC message to /track/{track_numbers[i]}/pan with value {pan_offset}: {e}")

    send_osc_message(f"/track/{track_numbers[i]}/fx/2/fxparam/8/value",
                     default_azimuth, time.time(), last_sent_azimuth,
                     last_azimuth_send_time) # Azimuth for tracks 2-10, FX slot 2
    send_osc_message(f"/track/{track_numbers[i]}/fx/2/fxparam/9/value",
                     default_elevation, time.time(), last_sent_elevation,
                     last_elevation_send_time) # Elevation for tracks 2-10, FX slot 2

send_osc_message(f"/track/{master_track_number}/reverb/drywet", master_reverb_drywet_off, time.time(), None,
                 None) # Master Reverb (Track 1)
# Initialize Master FX Param 12 to FX slot 1
send_osc_message(f"/track/{master_track_number}/fx/1/fxparam/12/value",
                 master_fx_param_12_value, time.time(), None, None) # Master FX Param 12 (Track 1, FX slot 1)

# Restore original fader control state
vpython_control_faders_enabled = original_fader_control_state

time.sleep(0.1)

scene.center = vector(0, 0, 0)
scene.autoscale = False
scene.range = 5
scene.width = 1900
scene.height = 800
scene.background = color.black

# Initialize scene light source and store its reference
# Set scene.lights to an empty list to use custom light sources
scene.lights = []
master_light = distant_light(direction=vector(0.5, 0.5, 0.5), color=color.white * 0.5) # Initial brightness

dt = 0.005
t = 0

g = vector(0, -30, 0)
plane_cor = 0.6
friction_coefficient_plane = 0.15

# Increase plane size
plane_length = 12 * 2
plane_width = 12 * 2
plane_thickness = 0.1
plane_color = color.cyan
plane_opacity = 0

ground = box(pos=vector(0, 0, 0), length=plane_length, height=plane_thickness, width=plane_width,
             color=plane_color, opacity=plane_opacity)

original_ground_opacity = ground.opacity

ground_y_top_world = ground.pos.y + plane_thickness / 2

# Ring restitution coefficient range
ring_cor_min_val = 0.3
ring_cor_max_val = 0.9


# Function to generate random initial positions and velocities for rings
def generate_random_ring_initials(ring_radius_val):
    # Ensure rings are spawned within the plane's bounds
    max_x_spawn = plane_length / 2 - ring_radius_val
    max_z_spawn = plane_width / 2 - ring_radius_val

    rand_x = random.uniform(-max_x_spawn, max_x_spawn)
    rand_z = random.uniform(-max_z_spawn, max_z_spawn)

    # Randomly generate Y-axis position: from flush with the plane to a certain height above
    min_y_spawn = ground_y_top_world + ring_thickness / 2
    max_initial_spawn_height_above_plane = 10
    rand_y = random.uniform(min_y_spawn, min_y_spawn + max_initial_spawn_height_above_plane)

    initial_pos = vector(rand_x, rand_y, rand_z)

    # Random initial velocity
    initial_vel = vector(random.uniform(-2, 2), 0, random.uniform(-2, 2))
    initial_angular_vel = vector(0, random.uniform(-3, 3), 0)

    return initial_pos, initial_vel, initial_angular_vel


# Properties for the first ring
ring_radius = 2 * 2
ring_thickness = 0.1
ring_base_color = color.red
ring_color = color.white

ring_glow_color = color.white
ring_glow_opacity = 0.0
ring_glow_fade_speed = 5.0
ring_glow_obj = ring(pos=vector(0, 0, 0),
                     radius=ring_radius,
                     thickness=ring_thickness * 0.8,
                     color=ring_glow_color,
                     axis=vector(0, 1, 0),
                     opacity=ring_glow_opacity)

dot_radius = 0.2
dot_color = color.white

ring_y_pos_world = ground_y_top_world + ring_thickness / 2

ring_vobj = ring(pos=vector(0, 0, 0),
                 radius=ring_radius,
                 thickness=ring_thickness,
                 color=ring_color,
                 axis=vector(0, 1, 0),
                 opacity=0.7)

original_ring_opacity = ring_vobj.opacity

dot_offset_from_ring_edge = 0.5
dot_vobj = sphere(pos=vector(ring_radius + dot_offset_from_ring_edge, 0, 0),
                  radius=dot_radius,
                  color=dot_color,
                  opacity=0.5)

# Use randomly generated position and velocity
pos1, vel1, angular_vel1 = generate_random_ring_initials(ring_radius)
rotating_object = compound([ring_vobj, dot_vobj, ring_glow_obj], pos=pos1)
rotating_object.vel = vel1
rotating_object.angular_vel = angular_vel1
rotating_object.mass = ring_mass # Set ring mass
# Store references to internal objects and pulse parameters
rotating_object.ring_vobj = ring_vobj
rotating_object.ring_glow_obj = ring_glow_obj
rotating_object.base_radius = ring_radius
rotating_object.current_radius_scale = 1.0
rotating_object.target_radius_scale = 1.0
rotating_object.pulse_speed = 0.1
rotating_object.pulse_decay_speed = 0.05

# Properties for the second ring
ring_radius_2 = ring_radius * (2 / 3)
ring_color_2 = color.black
ring_glow_color_2 = color.orange
ring_glow_opacity_2 = 0.0
ring_glow_obj_2 = ring(pos=vector(0, 0, 0),
                       radius=ring_radius_2 * 1.05,
                       thickness=ring_thickness * 0.8,
                       color=ring_glow_color_2,
                       axis=vector(0, 1, 0),
                       opacity=ring_glow_opacity_2)

dot_radius_2 = dot_radius * (2 / 3)
dot_color_2 = color.white

ring_vobj_2 = ring(pos=vector(0, 0, 0),
                   radius=ring_radius_2,
                   thickness=ring_thickness,
                   color=ring_color_2,
                   axis=vector(0, 1, 0),
                   opacity=0.7)

dot_vobj_2 = sphere(pos=vector(ring_radius_2 + dot_offset_from_ring_edge * (2 / 3), 0, 0),
                    radius=dot_radius_2,
                    color=dot_color_2,
                    opacity=0.5)

# Use randomly generated position and velocity
pos2, vel2, angular_vel2 = generate_random_ring_initials(ring_radius_2)
rotating_object_2 = compound([ring_vobj_2, dot_vobj_2, ring_glow_obj_2], pos=pos2)
rotating_object_2.vel = vel2
rotating_object_2.angular_vel = angular_vel2
rotating_object_2.mass = ring_mass # Set ring mass
# Store references to internal objects and pulse parameters
rotating_object_2.ring_vobj = ring_vobj_2
rotating_object_2.ring_glow_obj = ring_glow_obj_2
rotating_object_2.base_radius = ring_radius_2
rotating_object_2.current_radius_scale = 1.0
rotating_object_2.target_radius_scale = 1.0
rotating_object_2.pulse_speed = 0.1
rotating_object_2.pulse_decay_speed = 0.05

# Properties for the third ring
ring_radius_3 = ring_radius * 0.75
ring_color_3 = color.gray(0.5)
ring_glow_color_3 = color.green
ring_glow_opacity_3 = 0.0
ring_glow_obj_3 = ring(pos=vector(0, 0, 0),
                       radius=ring_radius_3 * 1.05,
                       thickness=ring_thickness * 0.8,
                       color=ring_glow_color_3,
                       axis=vector(0, 1, 0),
                       opacity=ring_glow_opacity_3)

dot_radius_3 = dot_radius * 0.75
dot_color_3 = color.white

ring_vobj_3 = ring(pos=vector(0, 0, 0),
                   radius=ring_radius_3,
                   thickness=ring_thickness,
                   color=ring_color_3,
                   axis=vector(0, 1, 0),
                   opacity=0.7)

dot_vobj_3 = sphere(pos=vector(ring_radius_3 + dot_offset_from_ring_edge * 0.75, 0, 0),
                    radius=dot_radius_3,
                    color=dot_color_3,
                    opacity=0.5)

# Use randomly generated position and velocity
pos3, vel3, angular_vel3 = generate_random_ring_initials(ring_radius_3)
rotating_object_3 = compound([ring_vobj_3, dot_vobj_3, ring_glow_obj_3], pos=pos3)
rotating_object_3.vel = vel3
rotating_object_3.angular_vel = angular_vel3
rotating_object_3.mass = ring_mass # Set ring mass
# Store references to internal objects and pulse parameters
rotating_object_3.ring_vobj = ring_vobj_3
rotating_object_3.ring_glow_obj = ring_glow_obj_3
rotating_object_3.base_radius = ring_radius_3
rotating_object_3.current_radius_scale = 1.0
rotating_object_3.target_radius_scale = 1.0
rotating_object_3.pulse_speed = 0.1
rotating_object_3.pulse_decay_speed = 0.05

# Properties for the fourth ring
ring_radius_4 = ring_radius * 0.5
ring_color_4 = color.gray(0.8)
ring_glow_color_4 = color.purple
ring_glow_opacity_4 = 0.0
ring_glow_obj_4 = ring(pos=vector(0, 0, 0),
                       radius=ring_radius_4 * 1.05,
                       thickness=ring_thickness * 0.8,
                       color=ring_glow_color_4,
                       axis=vector(0, 1, 0),
                       opacity=ring_glow_opacity_4)

dot_radius_4 = dot_radius * 0.5
dot_color_4 = color.white

ring_vobj_4 = ring(pos=vector(0, 0, 0),
                   radius=ring_radius_4,
                   thickness=ring_thickness,
                   color=ring_color_4,
                   axis=vector(0, 1, 0),
                   opacity=0.7)

dot_vobj_4 = sphere(pos=vector(ring_radius_4 + dot_offset_from_ring_edge * 0.5, 0, 0),
                    radius=dot_radius_4,
                    color=dot_color_4,
                    opacity=0.5)

# Use randomly generated position and velocity
pos4, vel4, angular_vel4 = generate_random_ring_initials(ring_radius_4)
rotating_object_4 = compound([ring_vobj_4, dot_vobj_4, ring_glow_obj_4], pos=pos4)
rotating_object_4.vel = vel4
rotating_object_4.angular_vel = angular_vel4
rotating_object_4.mass = ring_mass # Set ring mass
# Store references to internal objects and pulse parameters
rotating_object_4.ring_vobj = ring_vobj_4
rotating_object_4.ring_glow_obj = ring_glow_obj_4
rotating_object_4.base_radius = ring_radius_4
rotating_object_4.current_radius_scale = 1.0
rotating_object_4.target_radius_scale = 1.0
rotating_object_4.pulse_speed = 0.1
rotating_object_4.pulse_decay_speed = 0.05

constant_torque_magnitude = 0.025

BALL_SIZES = [0.06, 0.07, 0.08, 0.09]

# Ball colors, only black, yellow, white
ball_quadrant_colors = [
    color.black,
    color.yellow,
    color.white
]

inner_ball_cor = 0.8
inner_ball_friction = 0.1

inner_balls = [] # List of small balls for the first ring
inner_balls_2 = [] # List of small balls for the second ring
inner_balls_3 = [] # List of small balls for the third ring
inner_balls_4 = [] # List of small balls for the fourth ring

MAX_BALLS = 40
MAX_SPLIT_EVENTS_PER_BALL = 1
MIN_BALL_RADIUS = 0.02

SPLIT_COOLDOWN = 0.5

ball_contact_timers = {} # Ball contact timer
PROLONGED_CONTACT_THRESHOLD = 0.5
RAPID_SEPARATION_SPEED = 20.0

ring_contact_timers = {} # Ring contact timer
PROLONGED_RING_CONTACT_THRESHOLD = 0.1
RING_SEPARATION_SPEED = 10.0

# Create normal indicators for each ring (hidden)
ring_normal_indicator_1 = cylinder(pos=rotating_object.pos,
                                   axis=rotating_object.up.norm() * 1.0,
                                   radius=0.05,
                                   color=color.red,
                                   opacity=0.8,
                                   visible=False)

ring_normal_indicator_2 = cylinder(pos=rotating_object_2.pos,
                                   axis=rotating_object_2.up.norm() * 1.0,
                                   radius=0.05,
                                   color=color.blue,
                                   opacity=0.8,
                                   visible=False)

ring_normal_indicator_3 = cylinder(pos=rotating_object_3.pos,
                                   axis=rotating_object_3.up.norm() * 1.0,
                                   radius=0.05,
                                   color=color.green,
                                   opacity=0.8,
                                   visible=False)

ring_normal_indicator_4 = cylinder(pos=rotating_object_4.pos,
                                   axis=rotating_object_4.up.norm() * 1.0,
                                   radius=0.05,
                                   color=color.purple,
                                   opacity=0.8,
                                   visible=False)

release_speed = 30.0

last_event_trigger_time = time.time()
event_phase = "normal"
release_velocity_applied = False


class Particle:
    def __init__(self, pos, vel, radius, color, lifespan):
        self.vobj = sphere(pos=pos, radius=radius, color=color, opacity=1.0, emissive=True)
        self.vel = vel
        self.lifespan = lifespan
        self.creation_time = time.time()
        self.initial_opacity = 1.0


particles = []

shake_active = False
shake_start_time = 0
active_shake_duration = 0
active_shake_intensity = 0

camera_tracking_speed = 0.05
# Adjust camera offset to see all rings simultaneously
fixed_camera_offset = vector(0, 8, 8)
fixed_look_at_offset = vector(0, -4, 0)

clear_visual_effect_active = False
clear_visual_effect_start_time = 0
clear_visual_fade_duration = 0.3
clear_visual_restore_duration = 0.7

scene.camera.pos = vector(0, 5, 5)
scene.camera.axis = vector(0, -5, -5)

previous_tilt_angle_x = 0
previous_tilt_angle_z = 0

section_angle_span = (2 * pi) / 9


def lerp(start, end, t_val):
    return start * (1 - t_val) + end * t_val


def map_range(value, in_min, in_max, out_min, out_max):
    return out_min + (out_max - out_min) * ((value - in_min) / (in_max - in_min))


# Generic function to create new balls for any ring
def create_new_ball_for_ring(target_ring_obj, target_ring_radius, current_pos=None, current_vel=None,
                             collision_normal=None):
    initial_pos = vector(0, 0, 0)
    initial_vel = vector(0, 0, 0)

    current_ball_radius = random.choice(BALL_SIZES)

    if current_pos is None:
        max_spawn_offset = target_ring_radius - current_ball_radius - ring_thickness / 2 - 0.1
        rand_x = target_ring_obj.pos.x + (random.random() * 2 - 1) * max_spawn_offset
        rand_z = target_ring_obj.pos.z + (random.random() * 2 - 1) * max_spawn_offset
        initial_pos = vector(rand_x, ground_y_top_world + current_ball_radius + 0.01, rand_z)

        base_speed = 0.5

        dist_pos_x = (plane_length / 2) - initial_pos.x
        dist_neg_x = initial_pos.x - (-plane_length / 2)
        dist_pos_z = (plane_width / 2) - initial_pos.z
        dist_neg_z = initial_pos.z - (-plane_width / 2)

        min_dist_x = min(abs(dist_pos_x), abs(dist_neg_x))
        min_dist_z = min(abs(dist_pos_z), abs(dist_neg_z))

        if min_dist_x < min_dist_z:
            if abs(dist_pos_x) == min_dist_x:
                initial_vel.x = -base_speed
            else:
                initial_vel.x = base_speed
            initial_vel.z = (random.random() * 2 - 1) * 0.1
        else:
            if abs(dist_pos_z) == min_dist_z:
                initial_vel.z = -base_speed
            else:
                initial_vel.z = base_speed
            initial_vel.x = (random.random() * 2 - 1) * 0.1

        initial_vel.x += random.uniform(-0.05, 0.05)
        initial_vel.z += random.uniform(-0.05, 0.05)

    else:
        offset_vec = vector(random.uniform(-0.1, 0.1), 0, random.uniform(-0.1, 0.1))
        initial_pos = current_pos + offset_vec

        speed = max(current_vel.mag, 1)

        temp_new_ball_dir = vector(random.uniform(-1, 1), 0, random.uniform(-1, 1)).hat

        if collision_normal is not None:
            if dot(temp_new_ball_dir, collision_normal) < 0:
                temp_new_ball_dir = temp_new_ball_dir - 2 * dot(temp_new_ball_dir, collision_normal) * collision_normal

        if temp_new_ball_dir.mag == 0:
            temp_new_ball_dir = vector(random.uniform(-1, 1), 0, random.uniform(-1, 1)).hat

        initial_vel = temp_new_ball_dir.hat * speed
        initial_vel.y = current_vel.y

    new_ball = sphere(pos=initial_pos,
                      radius=current_ball_radius,
                      color=color.yellow)
    new_ball.vel = initial_vel
    new_ball.times_split = 0
    new_ball.last_split_time = time.time()
    return new_ball


# Initial ball creation lines removed. Balls will only appear when "Add Ball" is pressed.
# inner_balls.append(create_new_ball_for_ring(rotating_object, ring_radius))
# inner_balls_2.append(create_new_ball_for_ring(rotating_object_2, ring_radius_2))
# inner_balls_3.append(create_new_ball_for_ring(rotating_object_3, ring_radius_3))
# inner_balls_4.append(create_new_ball_for_ring(rotating_object_4, ring_radius_4))

tilting_pivot_point = vector(0, ground.pos.y - plane_thickness / 2, 0)

# Fixed tilt angle values as sliders have been removed
max_tilt_angle_x = radians(15)
tilt_frequency_x = 0.8

max_tilt_angle_z = radians(10)
tilt_frequency_z = 0.6
tilt_phase_offset_z = math.pi / 2


def trigger_shake(intensity, duration):
    global shake_active, shake_start_time, active_shake_duration, active_shake_intensity
    if not shake_active or intensity > active_shake_intensity or \
            duration > (active_shake_duration - (time.time() - shake_start_time)):
        shake_active = True
        shake_start_time = time.time()
        active_shake_duration = duration
        active_shake_intensity = intensity


def set_gravity(s):
    global g
    g.y = -s.value
    trigger_shake(0.6, 0.2)


scene.append_to_caption('Gravity Strength: ')
gravity_slider = slider(min=10, max=50, value=abs(g.y), step=1, bind=set_gravity)
scene.append_to_caption(' ')


def set_friction(s):
    global friction_coefficient_plane, inner_ball_friction
    friction_coefficient_plane = s.value
    inner_ball_friction = s.value
    trigger_shake(0.2, 0.1)


scene.append_to_caption('Friction Coefficient: ')
friction_slider = slider(min=0, max=0.5, value=friction_coefficient_plane, step=0.01, bind=set_friction)
scene.append_to_caption('\n')


def set_decay_time(s):
    global decay_time
    decay_time = s.value
    trigger_shake(0.08, 0.15)


scene.append_to_caption('Volume Decay Time (s): ')
decay_time_slider = slider(min=0.1, max=1.0, value=decay_time, step=0.05, bind=set_decay_time)
scene.append_to_caption('\n\n')


def add_ball_action():
    # Randomly select a ring to add a ball to
    target_ring_index = random.randint(0, 3)
    if target_ring_index == 0:
        if len(inner_balls) < MAX_BALLS:
            inner_balls.append(create_new_ball_for_ring(rotating_object, ring_radius))
            trigger_shake(0.06, 0.05)
    elif target_ring_index == 1:
        if len(inner_balls_2) < MAX_BALLS:
            inner_balls_2.append(create_new_ball_for_ring(rotating_object_2, ring_radius_2))
            trigger_shake(0.06, 0.05)
    elif target_ring_index == 2:
        if len(inner_balls_3) < MAX_BALLS:
            inner_balls_3.append(create_new_ball_for_ring(rotating_object_3, ring_radius_3))
            trigger_shake(0.06, 0.05)
    else:
        if len(inner_balls_4) < MAX_BALLS:
            inner_balls_4.append(create_new_ball_for_ring(rotating_object_4, ring_radius_4))
            trigger_shake(0.06, 0.05)


scene.append_to_caption(' ')
button(text='Add Ball (A)', bind=add_ball_action)
scene.append_to_caption('   ')


def clear_all_balls_action():
    global inner_balls, particles, inner_balls_2, inner_balls_3, inner_balls_4, event_phase, release_velocity_applied, clear_visual_effect_active, clear_visual_effect_start_time, quadrant_volume_clearing, quadrant_clear_start_time, quadrant_clear_initial_volume
    for ball in inner_balls:
        ball.visible = False
    inner_balls = []
    for ball in inner_balls_2:
        ball.visible = False
    inner_balls_2 = []
    for ball in inner_balls_3:
        ball.visible = False
    inner_balls_3 = []
    for ball in inner_balls_4:
        ball.visible = False
    inner_balls_4 = []
    for p in particles:
        p.vobj.visible = False
    particles = []
    event_phase = "normal"
    release_velocity_applied = False

    clear_visual_effect_active = True
    clear_visual_effect_start_time = time.time()
    trigger_shake(2.0, 0.3)
    print("All balls and particles cleared, event phase reset to normal.")

    # Clear projected sound sources and labels (now keyed by track number)
    # When clearing all balls, Ambisonics spheres and labels should also disappear
    for track_num in list(projected_sound_sources.keys()):
        if track_num in projected_sound_sources:
            projected_sound_sources[track_num].visible = False
        if track_num in projected_sound_labels:
            projected_sound_labels[track_num].visible = False


    # New: Turn off sound for all tracks (fades out over 3 seconds)
    current_time = time.time()
    for i in range(len(track_numbers)):
        # Store current volume to decay from
        quadrant_clear_initial_volume[i] = quadrant_volumes[i]
        quadrant_clear_start_time[i] = current_time
        quadrant_volume_clearing[i] = True # Activate clearing decay state

        # Immediately reset Azimuth and Elevation to default values
        quadrant_azimuths[i] = default_azimuth
        quadrant_elevations[i] = default_elevation
        send_osc_message(f"/track/{track_numbers[i]}/fx/2/fxparam/8/value", default_azimuth, current_time,
                         last_sent_azimuth, last_azimuth_send_time)
        send_osc_message(f"/track/{track_numbers[i]}/fx/2/fxparam/9/value", default_elevation, current_time,
                         last_sent_elevation, last_elevation_send_time)
        # Reset their trigger times so they can be triggered again after cooldown
        quadrant_azimuth_last_trigger_time[i] = -1.0
        quadrant_elevation_last_trigger_time[i] = -1.0


scene.append_to_caption(' ')
button(text='Clear All Balls (C)', bind=clear_all_balls_action)
scene.append_to_caption('   ')


def release_balls_action():
    global event_phase, last_event_trigger_time, reverb_active_time, release_velocity_applied, master_fx_param_12_state, master_fx_param_12_start_time, master_fx_param_12_value
    if event_phase == "normal":
        event_phase = "releasing"
        last_event_trigger_time = time.time()
        trigger_shake(1.6, 0.2)
        # Master Reverb dry/wet for track 1
        send_osc_message(f"/track/{master_track_number}/reverb/drywet", master_reverb_drywet_on, time.time(), None,
                         None)
        reverb_active_time = time.time()
        # Send /marker message directly, no optimization
        try:
            osc_client.send_message("/marker/2/play", 1)
        except Exception as e:
            print(f"Error sending OSC message to /marker/2/play with value 1: {e}")

        release_velocity_applied = False

        # Start master FX param 12 ramp up for track 1, FX slot 1
        master_fx_param_12_start_time = time.time()
        master_fx_param_12_state = "ramping_up"
        master_fx_param_12_value = 0.0

        # New ring random ejection logic
        min_ring_release_speed = 10.0
        max_ring_release_speed = 20.0

        # Apply random velocity to the first ring
        random_dir_1 = vector(random.uniform(-1, 1), random.uniform(-0.5, 0.5), random.uniform(-1, 1)).norm()
        random_speed_1 = random.uniform(min_ring_release_speed, max_ring_release_speed)
        rotating_object.vel = random_dir_1 * random_speed_1

        # Apply random velocity to the second ring
        random_dir_2 = vector(random.uniform(-1, 1), random.uniform(-0.5, 0.5), random.uniform(-1, 1)).norm()
        random_speed_2 = random.uniform(min_ring_release_speed, max_ring_release_speed)
        rotating_object_2.vel = random_dir_2 * random_speed_2

        # Apply random velocity to the third ring
        random_dir_3 = vector(random.uniform(-1, 1), random.uniform(-0.5, 0.5), random.uniform(-1, 1)).norm()
        random_speed_3 = random.uniform(min_ring_release_speed, max_ring_release_speed)
        rotating_object_3.vel = random_dir_3 * random_speed_3

        # Apply random velocity to the fourth ring
        random_dir_4 = vector(random.uniform(-1, 1), random.uniform(-0.5, 0.5), random.uniform(-1, 1)).norm()
        random_speed_4 = random.uniform(min_ring_release_speed, max_ring_release_speed)
        rotating_object_4.vel = random_dir_4 * random_speed_4

        print("Manually triggered: Starting Release Phase!")
    else:
        print(f"Current phase is '{event_phase}', cannot start release.")


scene.append_to_caption(' ')
button(text='Release Balls (R)', bind=release_balls_action)
scene.append_to_caption('   ')


# Define reaper_play_action and reaper_stop_action functions here
def reaper_play_action():
    # Send /play message directly, no optimization
    try:
        osc_client.send_message("/play", 1)
        print("REAPER: Play")
    except Exception as e:
        print(f"Error sending OSC message to /play with value 1: {e}")


def reaper_stop_action():
    # Send /stop message directly, no optimization
    try:
        osc_client.send_message("/stop", 1)
        print("REAPER: Stop")
    except Exception as e:
        print(f"Error sending OSC message to /stop with value 1: {e}")


scene.append_to_caption(' ')
button(text='REAPER Play', bind=reaper_play_action)
scene.append_to_caption('   ')

scene.append_to_caption(' ')
button(text='REAPER Stop', bind=reaper_stop_action)
scene.append_to_caption('   ')

# New: Button to toggle VPython control of track faders
def toggle_vpython_fader_control():
    global vpython_control_faders_enabled, reaper_track_volumes, quadrant_volumes, track_numbers
    vpython_control_faders_enabled = not vpython_control_faders_enabled
    print(f"VPython Fader Control is {'Enabled' if vpython_control_faders_enabled else 'Disabled'}")
    if not vpython_control_faders_enabled:
        # If control is disabled, copy VPython's internal volume state to reaper_track_volumes for visualization
        for i, track_num in enumerate(track_numbers):
            reaper_track_volumes[track_num] = quadrant_volumes[i]
        print("Ambisonics sphere state locked to current visual state.")
    else:
        # If control is enabled, ensure VPython's internal volume is synchronized with REAPER's current volume
        for i, track_num in enumerate(track_numbers):
            quadrant_volumes[i] = reaper_track_volumes.get(track_num, 0.0)
        print("Ambisonics sphere state will be controlled by VPython internal logic.")

scene.append_to_caption(' ')
button(text='Toggle VPython Fader Control', bind=toggle_vpython_fader_control)
scene.append_to_caption('   ')

# New: Button to toggle ball attraction strength
def toggle_attraction_strength():
    global ball_attraction_strength, current_attraction_state, attraction_toggle_button
    if current_attraction_state == "small":
        ball_attraction_strength = LARGE_ATTRACTION_STRENGTH
        current_attraction_state = "large"
        attraction_toggle_button.text = f'Ball Attraction: Large ({LARGE_ATTRACTION_STRENGTH:.1f})'
        print(f"Ball attraction strength set to: Large ({ball_attraction_strength:.1f})")
    else:
        ball_attraction_strength = SMALL_ATTRACTION_STRENGTH
        current_attraction_state = "small"
        attraction_toggle_button.text = f'Ball Attraction: Small ({SMALL_ATTRACTION_STRENGTH:.1f})'
        print(f"Ball attraction strength set to: Small ({ball_attraction_strength:.1f})")
    trigger_shake(0.1, 0.1)

scene.append_to_caption(' ')
attraction_toggle_button = button(text=f'Ball Attraction: Small ({SMALL_ATTRACTION_STRENGTH:.1f})', bind=toggle_attraction_strength)
scene.append_to_caption('\n')


def apply_collision_response(obj_vel, normal, cor, friction_coeff, dt, mass=1.0):
    """Applies collision response to an object's velocity."""
    v_normal = dot(obj_vel, normal) * normal
    v_tangent = obj_vel - v_normal

    v_normal_after_bounce = -v_normal * cor

    if v_tangent.mag > 0:
        normal_force_magnitude = g.mag * mass
        friction_magnitude = friction_coeff * normal_force_magnitude
        friction_acceleration_vector = -v_tangent.norm() * friction_magnitude * dt

        if friction_acceleration_vector.mag >= v_tangent.mag:
            v_tangent = vector(0, 0, 0)
        else:
            v_tangent += friction_acceleration_vector

    return v_normal_after_bounce + v_tangent


def handle_ball_ground_collision(ball):
    """Handles collision between a ball and the ground plane."""
    ground_normal = ground.up.norm()
    distance_ball_to_plane_top = dot(ball.pos - (ground.pos + (plane_thickness / 2) * ground_normal),
                                     ground_normal)

    if distance_ball_to_plane_top < ball.radius and dot(ball.vel, ground_normal) < 0:
        projection_on_plane_top_ball = ball.pos - distance_ball_to_plane_top * ground_normal
        ball.pos = projection_on_plane_top_ball + ball.radius * ground_normal

        ball.vel = apply_collision_response(ball.vel, ground_normal, inner_ball_cor, inner_ball_friction, dt)


# Generic function to handle ring physics
def handle_ring_physics_for_object(ring_obj, current_ring_radius):
    """Applies physics (gravity, angular momentum, collisions) to a ring object."""
    ring_obj.vel += g * dt
    ring_obj.pos += ring_obj.vel * dt

    # Simplified angular momentum: maintain constant torque and apply additional impulse on collision
    ring_obj.angular_vel += ring_obj.up.norm() * constant_torque_magnitude * dt
    ring_obj.rotate(angle=ring_obj.angular_vel.mag * dt,
                    axis=ring_obj.angular_vel.norm(),
                    origin=ring_obj.pos)

    ground_normal = ground.up.norm()
    distance_center_to_plane_top = dot(ring_obj.pos - (ground.pos + (plane_thickness / 2) * ground_normal),
                                       ground_normal)
    min_distance_for_no_penetration = ring_thickness / 2

    if distance_center_to_plane_top < min_distance_for_no_penetration:
        projection_on_plane_top = ring_obj.pos - distance_center_to_plane_top * ground_normal
        ring_obj.pos = projection_on_plane_top + min_distance_for_no_penetration * ground_normal

        if dot(ring_obj.vel, ground_normal) < 0:
            # Calculate ring restitution coefficient: smaller radius, higher restitution coefficient
            all_ring_radii = [ring_radius, ring_radius_2, ring_radius_3, ring_radius_4]
            min_overall_radius = min(all_ring_radii)
            max_overall_radius = max(all_ring_radii)

            if max_overall_radius == min_overall_radius:
                current_ring_cor = ring_cor_max_val # If all ring radii are the same, use max restitution coefficient
            else:
                # Normalize current ring radius to [0, 1] range, 0 for min radius, 1 for max radius
                normalized_radius = (current_ring_radius - min_overall_radius) / (
                        max_overall_radius - min_overall_radius)
                # Use lerp function to map normalized radius to restitution coefficient range, achieving higher restitution for smaller radii
                current_ring_cor = lerp(ring_cor_max_val, ring_cor_min_val, normalized_radius)

            ring_obj.vel = apply_collision_response(ring_obj.vel, ground_normal, current_ring_cor,
                                                    friction_coefficient_plane, dt)

    ground_local_x_axis = ground.axis.norm()
    ground_local_z_axis = cross(ground_normal, ground_local_x_axis).norm()

    vec_ring_to_ground_center = ring_obj.pos - ground.pos
    local_x = dot(vec_ring_to_ground_center, ground_local_x_axis)
    local_z = dot(vec_ring_to_ground_center, ground_local_z_axis)

    max_x_bound = plane_length / 2 - current_ring_radius
    max_z_bound = plane_width / 2 - current_ring_radius

    if abs(local_x) > max_x_bound:
        clamped_x = max_x_bound * sign(local_x)
        correction_vec_x = (clamped_x - local_x) * ground_local_x_axis
        ring_obj.pos += correction_vec_x
        ring_obj.vel -= 2 * dot(ring_obj.vel, ground_local_x_axis) * ground_local_x_axis * 0.5

    if abs(local_z) > max_z_bound:
        clamped_z = max_z_bound * sign(local_z)
        correction_vec_z = (clamped_z - local_z) * ground_local_z_axis
        ring_obj.pos += correction_vec_z
        ring_obj.vel -= 2 * dot(ring_obj.vel, ground_local_z_axis) * ground_local_z_axis * 0.5


# New: Define a list of all rings for volume control toggling
ring_objects_list = [rotating_object, rotating_object_2, rotating_object_3, rotating_object_4]


# Generic function to handle ball-ring collisions
def handle_ball_ring_collision_for_object(ball, ring_obj, ring_radius_val, ring_glow_obj_val, ring_vobj_val,
                                          current_time, balls_to_add, balls_to_remove):
    """
    Handles collision between a ball and a ring.
    Updates ball velocity, ring angular velocity, and triggers sound/visual effects.
    """
    vec_ball_to_ring_center_xz = vector(ball.pos.x - ring_obj.pos.x, 0,
                                        ball.pos.z - ring_obj.pos.z)
    ball_horizontal_dist = vec_ball_to_ring_center_xz.mag

    ring_inner_radius_effective = ring_radius_val - ring_thickness / 2

    if ball_horizontal_dist > ring_inner_radius_effective - ball.radius:
        collision_normal_xz = vec_ball_to_ring_center_xz.norm()
        penetration_depth = (ball_horizontal_dist + ball.radius) - ring_inner_radius_effective
        ball.pos -= penetration_depth * vector(collision_normal_xz.x, 0, collision_normal_xz.z)

        if id(ball) not in ring_contact_timers:
            ring_contact_timers[id(ball)] = current_time
        else:
            contact_duration = current_time - ring_contact_timers[id(ball)]
            if contact_duration > PROLONGED_CONTACT_THRESHOLD:
                separation_direction = -collision_normal_xz
                ball.vel = separation_direction * RING_SEPARATION_SPEED
                ring_contact_timers.pop(id(ball), None)
                return

        ball_vel_xz = vector(ball.vel.x, 0, ball.vel.z)
        ball.vel = vector(
            apply_collision_response(ball_vel_xz, collision_normal_xz, inner_ball_cor, inner_ball_friction, dt).x,
            ball.vel.y,
            apply_collision_response(ball_vel_xz, collision_normal_xz, inner_ball_cor, inner_ball_friction, dt).z)

        # Apply simplified angular momentum impulse to the ring
        # Calculate tangential velocity of the ball relative to the ring's center
        r_vec = vector(ball.pos.x - ring_obj.pos.x, 0, ball.pos.z - ring_obj.pos.z)
        if r_vec.mag > 0:
            r_vec_norm = r_vec.norm()
            # Tangential direction perpendicular to the radius vector
            tangential_direction = vector(-r_vec_norm.z, 0, r_vec_norm.x)
            # Component of ball's velocity in the tangential direction
            ball_tangential_speed = dot(ball_vel_xz, tangential_direction)

            if abs(ball_tangential_speed) > 0.1: # Only apply impulse if there's sufficient tangential speed
                # Impulse magnitude related to ball's tangential speed and a random factor
                angular_impulse_magnitude = (abs(ball_tangential_speed) / 100.0) * random.uniform(0.01, 0.05)
                # Impulse direction depends on the direction of tangential speed
                ring_obj.angular_vel.y += angular_impulse_magnitude * sign(ball_tangential_speed)
            else: # If tangential speed is very small, apply a tiny random impulse
                ring_obj.angular_vel.y += random.uniform(-0.005, 0.005)

        relative_ball_pos = ball.pos - ring_obj.pos
        ring_local_up_axis = ring_obj.axis.norm()
        temp_ref = vector(1, 0, 0) if abs(dot(ring_local_up_axis, vector(1, 0, 0))) < 0.9 else vector(0, 0, 1)
        ring_local_right_axis = cross(ring_local_up_axis, temp_ref).norm()
        ring_local_forward_axis = cross(ring_local_right_axis, ring_local_up_axis).norm()

        local_x_component = dot(relative_ball_pos, ring_local_right_axis)
        local_z_component = dot(relative_ball_pos, ring_local_forward_axis)

        normalized_pan_pos = local_x_component / ring_radius_val

        collision_angle_local = atan2(local_z_component, local_x_component)
        if collision_angle_local < 0:
            collision_angle_local += 2 * pi

        hit_quadrant = int(collision_angle_local / section_angle_span)
        hit_quadrant = min(hit_quadrant, len(track_numbers) - 1)

        # Override clear decay if a hit occurs
        if quadrant_volume_clearing[hit_quadrant]:
            quadrant_volume_clearing[hit_quadrant] = False # Stop clear decay

        quadrant_volumes[hit_quadrant] = max_volume
        quadrant_decay_timers[hit_quadrant] = time.time()

        # Azimuth control with cooldown (re-enabled and range adjusted)
        if current_time - quadrant_azimuth_last_trigger_time[hit_quadrant] > azimuth_elevation_cooldown_time:
            # Extend Azimuth range to 0 to 0.99
            azimuth_degrees = map_range(normalized_pan_pos, -1.0, 1.0, 0.0, 0.99)
            quadrant_azimuths[hit_quadrant] = azimuth_degrees # Set current Azimuth value
            quadrant_azimuth_last_trigger_time[hit_quadrant] = current_time # Update last trigger time

        # Elevation control with cooldown (re-enabled and range adjusted)
        if current_time - quadrant_elevation_last_trigger_time[hit_quadrant] > azimuth_elevation_cooldown_time:
            min_y_for_elevation = ground_y_top_world # Ground height
            max_y_for_elevation = ground_y_top_world + 15 # Assume ring can bounce up to this height

            # Normalize ring's Y-axis position to [0, 1]
            normalized_ring_y = map_range(ring_obj.pos.y, min_y_for_elevation, max_y_for_elevation, 0.0, 1.0)

            # Map normalized Y-axis position to elevation range (e.g., 0 to 0.99)
            elevation_degrees = map_range(normalized_ring_y, 0.0, 1.0, 0.0, 0.99)
            quadrant_elevations[hit_quadrant] = elevation_degrees # Set current Elevation value
            quadrant_elevation_last_trigger_time[hit_quadrant] = current_time # Update last trigger time

        # Set ball color to white
        ball.color = color.white

        # Update ring glow and ring color
        # Increase glow clarity and fix to white
        ring_glow_obj_val.opacity = min(ball.vel.mag / 15.0, 0.8)
        ring_glow_obj_val.color = color.white
        ring_vobj_val.color = color.white

        # Trigger ring pulse effect
        ring_obj.target_radius_scale = 1.1 # Set pulse target size

        if ball.times_split < MAX_SPLIT_EVENTS_PER_BALL and \
                len(balls_to_add) + len(inner_balls) + len(inner_balls_2) + len(inner_balls_3) + len(
            inner_balls_4) < MAX_BALLS and \
                (time.time() - ball.last_split_time > SPLIT_COOLDOWN):

            new_ball = create_new_ball_for_ring(ring_obj, ring_radius_val, ball.pos, ball.vel, collision_normal_xz)
            balls_to_add.append(new_ball)
            for _ in range(5):
                p_vel = vector(random.uniform(-1, 1), random.uniform(-1, 1),
                               random.uniform(-1, 1)).norm() * random.uniform(2, 5)
                # Particle color fixed to white
                particles.append(Particle(new_ball.pos, p_vel, random.uniform(0.01, 0.03), color.white,
                                          random.uniform(0.3, 0.6)))
    else:
        if id(ball) in ring_contact_timers:
            ring_contact_timers.pop(id(ball), None)


def handle_ball_ball_collision(ball1, ball2, balls_to_add, balls_to_remove):
    """Handles collision between two balls."""
    if ball1 in balls_to_remove or ball2 in balls_to_remove:
        return

    distance_between_balls = (ball1.pos - ball2.pos).mag
    min_distance_for_collision = ball1.radius + ball2.radius
    contact_key = frozenset({id(ball1), id(ball2)})

    if distance_between_balls < min_distance_for_collision:
        current_time = time.time()
        if contact_key not in ball_contact_timers:
            ball_contact_timers[contact_key] = current_time
        else:
            contact_duration = current_time - ball_contact_timers[contact_key]
            if contact_duration > PROLONGED_CONTACT_THRESHOLD:
                normal = (ball1.pos - ball2.pos).norm()
                ball1.vel = normal * RAPID_SEPARATION_SPEED
                ball2.vel = -normal * RAPID_SEPARATION_SPEED
                ball_contact_timers.pop(contact_key, None)
                return

        overlap = min_distance_for_collision - distance_between_balls
        if distance_between_balls == 0:
            normal = vector(random.uniform(-1, 1), 0, random.uniform(-1, 1)).norm()
            ball1.pos += normal * (ball1.radius * 0.01)
            ball2.pos -= normal * (ball2.radius * 0.01)
            distance_between_balls = (ball1.pos - ball2.pos).mag
            if distance_between_balls == 0: return
            normal = (ball1.pos - ball2.pos).norm()
        else:
            normal = (ball1.pos - ball2.pos).norm()

        ball1.pos += normal * (overlap / 2 + 0.005)
        ball2.pos -= normal * (overlap / 2 + 0.005)

        rv = ball2.vel - ball1.vel
        vel_along_normal = dot(rv, normal)

        if vel_along_normal > 0:
            return

        impulse_scalar = -(1 + inner_ball_cor) * vel_along_normal / 2
        impulse = impulse_scalar * normal

        ball1.vel -= impulse
        ball2.vel += impulse

        if impulse_scalar > 0.5:
            for _ in range(3):
                p_vel = vector(random.uniform(-1, 1), random.uniform(-1, 1),
                               random.uniform(-1, 1)).norm() * random.uniform(2, 5)
                # Particle color fixed to white
                particles.append(Particle((ball1.pos + ball2.pos) / 2, p_vel, random.uniform(0.01, 0.03), color.white,
                                          random.uniform(0.3, 0.6)))
    else:
        if contact_key in ball_contact_timers:
            ball_contact_timers.pop(contact_key, None)


def update_particles():
    """Updates the position and opacity of particles, removing expired ones."""
    global particles
    active_particles = []
    for p in particles:
        elapsed_p_time = time.time() - p.creation_time
        if elapsed_p_time < p.lifespan:
            p.vobj.pos += p.vel * dt
            p.vobj.opacity = p.initial_opacity * (1 - elapsed_p_time / p.lifespan)
            active_particles.append(p)
        else:
            p.vobj.visible = False
    particles = active_particles


# Generic function to update OSC parameters (simplified to handle shared track data only)
def update_osc_parameters(current_time):
    """Updates OSC parameters based on simulation state and sends messages to REAPER."""
    global reverb_active_time, quadrant_volumes, quadrant_decay_timers, \
        quadrant_azimuths, quadrant_elevations, quadrant_azimuth_last_trigger_time, quadrant_elevation_last_trigger_time, \
        quadrant_volume_clearing, quadrant_clear_start_time, quadrant_clear_initial_volume, \
        master_fx_param_12_value, master_fx_param_12_start_time, master_fx_param_12_state, vpython_control_faders_enabled

    if reverb_active_time != -1.0:
        elapsed_since_reverb_active = current_time - reverb_active_time

        if elapsed_since_reverb_active < reverb_full_wet_duration:
            current_reverb_wet = master_reverb_drywet_on
        elif elapsed_since_reverb_active < reverb_full_wet_duration + reverb_decay_duration:
            decay_progress = (elapsed_since_reverb_active - reverb_full_wet_duration) / reverb_decay_duration
            current_reverb_wet = master_reverb_drywet_on * (1 - decay_progress)
        else:
            current_reverb_wet = master_reverb_drywet_off
            reverb_active_time = -1.0 # Reset reverb timer here when it's fully off

        send_osc_message(f"/track/{master_track_number}/reverb/drywet", current_reverb_wet, current_time, None, None)

    for i in range(len(track_numbers)): # Now updating parameters for tracks 2-10
        # Volume decay logic
        if quadrant_volume_clearing[i]:
            elapsed_time = current_time - quadrant_clear_start_time[i]
            if elapsed_time < clear_volume_decay_duration:
                decay_progress = elapsed_time / clear_volume_decay_duration
                new_volume = lerp(quadrant_clear_initial_volume[i], 0.0, decay_progress)
                quadrant_volumes[i] = max(0, new_volume)
                # Only send volume if VPython fader control is enabled
                if vpython_control_faders_enabled:
                    send_osc_message(f"/track/{track_numbers[i]}/volume", quadrant_volumes[i], current_time,
                                     last_sent_volume, last_volume_send_time)
            else:
                quadrant_volumes[i] = 0.0
                if vpython_control_faders_enabled:
                    send_osc_message(f"/track/{track_numbers[i]}/volume", quadrant_volumes[i], current_time,
                                     last_sent_volume, last_volume_send_time)
                quadrant_volume_clearing[i] = False # Turn off clearing state
        elif quadrant_decay_timers[i] != -1: # Only apply normal decay if not in clearing state
            elapsed_time = current_time - quadrant_decay_timers[i]
            if elapsed_time < decay_time:
                decay_factor = 1 - (elapsed_time / decay_time)
                new_volume = max_volume * decay_factor
                quadrant_volumes[i] = max(0, new_volume)
                if vpython_control_faders_enabled:
                    send_osc_message(f"/track/{track_numbers[i]}/volume", quadrant_volumes[i], current_time,
                                     last_sent_volume, last_volume_send_time)
            else:
                if quadrant_volumes[i] > 0:
                    quadrant_volumes[i] = 0.0
                    if vpython_control_faders_enabled:
                        send_osc_message(f"/track/{track_numbers[i]}/volume", quadrant_volumes[i], current_time,
                                         last_sent_volume, last_volume_send_time)
                quadrant_decay_timers[i] = -1

        # Azimuth decay logic (now continuously decays, unaffected by cooldown)
        if abs(quadrant_azimuths[i] - default_azimuth) > 0.001:
            quadrant_azimuths[i] = lerp(quadrant_azimuths[i], default_azimuth, dt / azimuth_decay_time)
            if abs(quadrant_azimuths[i] - default_azimuth) < 0.001:
                quadrant_azimuths[i] = default_azimuth
        send_osc_message(f"/track/{track_numbers[i]}/fx/2/fxparam/8/value", quadrant_azimuths[i], current_time,
                         last_sent_azimuth, last_azimuth_send_time)

        # Elevation decay logic (now continuously decays, unaffected by cooldown)
        if abs(quadrant_elevations[i] - default_elevation) > 0.001:
            quadrant_elevations[i] = lerp(quadrant_elevations[i], default_elevation, dt / elevation_decay_time)
            if abs(quadrant_elevations[i] - default_elevation) < 0.001:
                quadrant_elevations[i] = default_elevation
        send_osc_message(f"/track/{track_numbers[i]}/fx/2/fxparam/9/value", quadrant_elevations[i], current_time,
                         last_sent_elevation, last_elevation_send_time)

    # Master FX Param 12 state machine
    if master_fx_param_12_state == "ramping_up":
        elapsed = current_time - master_fx_param_12_start_time
        progress = min(1.0, elapsed / master_fx_param_12_ramp_duration)
        master_fx_param_12_value = lerp(0.0, 1.0, progress)
        if progress >= 1.0:
            master_fx_param_12_state = "decaying" # Transition to decaying immediately after ramp up
            master_fx_param_12_start_time = current_time # Reset start time for decay phase
    elif master_fx_param_12_state == "decaying":
        elapsed = current_time - master_fx_param_12_start_time
        progress = min(1.0, elapsed / master_fx_param_12_decay_duration)
        master_fx_param_12_value = lerp(1.0, 0.0, progress)
        if progress >= 1.0:
            master_fx_param_12_state = "off"
            master_fx_param_12_value = 0.0 # Ensure it ends at 0

    # Send Master FX Param 12 OSC message to FX slot 1
    send_osc_message(f"/track/{master_track_number}/fx/1/fxparam/12/value", master_fx_param_12_value, current_time,
                     None, None)


# New: Apply attraction force to balls
def apply_attraction_force_to_ball(ball, ring_obj, strength):
    """Applies an attraction force to a ball, pulling it towards the ring's center."""
    # Calculate vector from ball to ring center in XZ plane
    vec_to_center_xz = vector(ring_obj.pos.x - ball.pos.x, 0, ring_obj.pos.z - ball.pos.z)
    distance_xz = vec_to_center_xz.mag

    if distance_xz > 0.1: # Avoid division by zero or excessively strong force at very close distances
        # Attraction force strength is proportional to distance (linear attraction)
        force_magnitude = strength * distance_xz

        # Apply force to ball's velocity
        attraction_force = vec_to_center_xz.norm() * force_magnitude
        ball.vel += attraction_force * dt # Apply force as acceleration


def update_ring_visuals(current_time):
    """Updates the visual properties of the rings, including pulse and opacity."""
    global ring_glow_opacity, ring_glow_obj, ring_vobj, ring_glow_opacity_2, ring_glow_obj_2, ring_vobj_2, \
        ring_glow_opacity_3, ring_glow_obj_3, ring_vobj_3, ring_glow_opacity_4, ring_glow_obj_4, ring_vobj_4, \
        clear_visual_effect_active, original_ring_opacity, original_ground_opacity

    if clear_visual_effect_active:
        elapsed_clear_time = current_time - clear_visual_effect_start_time

        if elapsed_clear_time < clear_visual_fade_duration:
            fade_progress = elapsed_clear_time / clear_visual_fade_duration
            ring_vobj.opacity = lerp(original_ring_opacity, 0.0, fade_progress)
            ground.opacity = lerp(original_ground_opacity, 0.0, fade_progress)
            ring_vobj_2.opacity = lerp(original_ring_opacity, 0.0, fade_progress)
            ring_vobj_3.opacity = lerp(original_ring_opacity, 0.0, fade_progress)
            ring_vobj_4.opacity = lerp(original_ring_opacity, 0.0, fade_progress)
        elif elapsed_clear_time < clear_visual_fade_duration + clear_visual_restore_duration:
            restore_progress = (elapsed_clear_time - clear_visual_fade_duration) / clear_visual_restore_duration
            ring_vobj.opacity = lerp(0.0, original_ring_opacity, restore_progress)
            ground.opacity = lerp(0.0, original_ground_opacity,
                                  restore_progress)
            ring_vobj_2.opacity = lerp(0.0, original_ring_opacity, restore_progress)
            ring_vobj_3.opacity = lerp(0.0, original_ring_opacity, restore_progress)
            ring_vobj_4.opacity = lerp(0.0, original_ring_opacity, restore_progress)
        else:
            clear_visual_effect_active = False
            ring_vobj.opacity = original_ring_opacity
            ground.opacity = original_ground_opacity
            ring_vobj_2.opacity = original_ring_opacity
            ring_vobj_3.opacity = original_ring_opacity
            ring_vobj_4.opacity = original_ring_opacity
        return

    # Update pulse and opacity for each ring
    for r_obj, base_r, quad_vols, base_color in [
        (rotating_object, ring_radius, quadrant_volumes, ring_base_color),
        (rotating_object_2, ring_radius_2, quadrant_volumes, ring_color_2),
        (rotating_object_3, ring_radius_3, quadrant_volumes, ring_color_3),
        (rotating_object_4, ring_radius_4, quadrant_volumes, ring_color_4)
    ]:
        # Pulse effect
        r_obj.current_radius_scale = lerp(r_obj.current_radius_scale, r_obj.target_radius_scale, r_obj.pulse_speed)
        r_obj.target_radius_scale = lerp(r_obj.target_radius_scale, 1.0, r_obj.pulse_decay_speed)
        r_obj.ring_vobj.radius = base_r * r_obj.current_radius_scale
        r_obj.ring_glow_obj.radius = (base_r * 1.05) * r_obj.current_radius_scale

        # Glow decay
        if r_obj.ring_glow_obj.opacity > 0:
            r_obj.ring_glow_obj.opacity -= ring_glow_fade_speed * dt
            if r_obj.ring_glow_obj.opacity < 0: r_obj.ring_glow_obj.opacity = 0

        # Ring body color restoration (now restores to initial ring color, not ball color)
        r_obj.ring_vobj.color = lerp(r_obj.ring_vobj.color, base_color, ring_glow_fade_speed * dt)


# Define camera modes
camera_modes = [
    "inside_ring_1", # View deep inside the ring
    "track_all", # Slightly further view
    "ambisonics_view" # Ambisonics top-down view
]
current_camera_mode_index = 0


def switch_camera_mode():
    """Switches the camera view mode."""
    global current_camera_mode_index
    current_camera_mode_index = (current_camera_mode_index + 1) % len(camera_modes)
    print(f"Switched camera mode to: {camera_modes[current_camera_mode_index]}")


scene.append_to_caption(' ')
button(text='Switch Camera Mode', bind=switch_camera_mode)
scene.append_to_caption('   ')


def update_camera(current_time):
    """Updates the camera's position and orientation based on current mode and shake effect."""
    global shake_active, shake_start_time, active_shake_duration, active_shake_intensity

    if shake_active:
        elapsed_shake_time = current_time - shake_start_time
        if elapsed_shake_time < active_shake_duration:
            current_shake_factor = 1 - (elapsed_shake_time / active_shake_duration)
            current_intensity = active_shake_intensity * current_shake_factor
            # Increase camera shake magnitude
            scene.camera.pos += vector(random.uniform(-1, 1), random.uniform(-1, 1),
                                       random.uniform(-1, 1)).norm() * current_intensity * 2.0
            scene.camera.axis += vector(random.uniform(-1, 1), random.uniform(-1, 1),
                                        random.uniform(-1, 1)).norm() * current_intensity * 1.0
        else:
            shake_active = False
            active_shake_intensity = 0

    target_center = vector(0, 0, 0)
    target_camera_pos = vector(0, 0, 0)
    target_look_at_pos = vector(0, 0, 0)

    # Calculate mid_point at the beginning of the function so it's always defined
    all_ring_positions = [rotating_object.pos, rotating_object_2.pos, rotating_object_3.pos, rotating_object_4.pos]
    mid_point = sum(all_ring_positions, vector(0, 0, 0)) / len(all_ring_positions)

    current_mode = camera_modes[current_camera_mode_index]

    if current_mode == "track_all":
        target_center = mid_point
        target_camera_pos = target_center + fixed_camera_offset
        target_look_at_pos = target_center + fixed_look_at_offset
    elif current_mode == "track_ring_1":
        target_center = rotating_object.pos
        target_camera_pos = target_center + vector(0, 5, 5)
        target_look_at_pos = target_center
    elif current_mode == "track_ring_2":
        target_center = rotating_object_2.pos
        target_camera_pos = target_center + vector(0, 5, 5)
        target_look_at_pos = target_center
    elif current_mode == "track_ring_3":
        target_center = rotating_object_3.pos
        target_camera_pos = target_center + vector(0, 5, 5)
        target_look_at_pos = target_center
    elif current_mode == "track_ring_4":
        target_center = rotating_object_4.pos
        target_camera_pos = target_center + vector(0, 5, 5)
        target_look_at_pos = target_center
    elif current_mode == "overhead_view":
        target_center = vector(0, 0, 0)
        target_camera_pos = target_center + vector(0, 20, 0)
        target_look_at_pos = target_center
    elif current_mode == "low_angle_view":
        target_center = vector(0, 0, 0)
        target_camera_pos = target_center + vector(0, 1, 15)
        target_look_at_pos = target_center + vector(0, 0, 0)
    elif current_mode == "inside_ring_1":
        target_center = rotating_object.pos
        # Camera inside the ring, looking at the ring center
        target_camera_pos = target_center + rotating_object.axis.norm() * (ring_radius / 2) + vector(0, 0.5, 0)
        target_look_at_pos = target_center
    elif current_mode == "side_view_plane":
        target_center = vector(0, 0, 0)
        # View from the side of the plane
        target_camera_pos = target_center + vector(plane_length / 2 + 5, 5, 0)
        target_look_at_pos = target_center
    elif current_mode == "ambisonics_view":
        target_center = hemisphere_center
        target_camera_pos = hemisphere_center + vector(0, hemisphere_radius * 1.5, hemisphere_radius * 1.5)
        target_look_at_pos = hemisphere_center

    if event_phase == "releasing":
        # During the release phase, the camera might zoom in or move to a more dynamic position
        # This camera behavior can override the current mode settings
        target_camera_pos = mid_point + vector(0, 10, 10) # Slightly pull back and raise
        target_look_at_pos = mid_point + vector(0, -2, -2)

    scene.camera.pos = lerp(scene.camera.pos, target_camera_pos, camera_tracking_speed)
    scene.camera.axis = lerp(scene.camera.axis, target_look_at_pos - scene.camera.pos, camera_tracking_speed)


dragging_object = None # Track the currently dragged object
drag_start_mouse_pos = vector(0, 0, 0)
drag_start_object_pos = vector(0, 0, 0)


def on_mousedown(evt):
    """Handles mouse down events for dragging rings."""
    global dragging_object, drag_start_mouse_pos, drag_start_object_pos
    if scene.mouse.pick == rotating_object:
        dragging_object = rotating_object
        drag_start_mouse_pos = scene.mouse.pos
        drag_start_object_pos = rotating_object.pos
    elif scene.mouse.pick == rotating_object_2:
        dragging_object = rotating_object_2
        drag_start_mouse_pos = scene.mouse.pos
        drag_start_object_pos = rotating_object_2.pos
    elif scene.mouse.pick == rotating_object_3:
        dragging_object = rotating_object_3
        drag_start_mouse_pos = scene.mouse.pos
        drag_start_object_pos = rotating_object_3.pos
    elif scene.mouse.pick == rotating_object_4:
        dragging_object = rotating_object_4
        drag_start_mouse_pos = scene.mouse.pos
        drag_start_object_pos = rotating_object_4.pos


def on_mousemove(evt):
    """Handles mouse move events for dragging rings."""
    global drag_start_mouse_pos, drag_start_object_pos
    if dragging_object and scene.mouse.pos:
        mouse_delta = scene.mouse.pos - drag_start_mouse_pos

        new_x = drag_start_object_pos.x + mouse_delta.x
        new_z = drag_start_object_pos.z + mouse_delta.z

        # Correction: Use the radius of the internal ring object of the dragging_object
        if dragging_object == rotating_object:
            current_drag_radius = ring_radius
        elif dragging_object == rotating_object_2:
            current_drag_radius = ring_radius_2
        elif dragging_object == rotating_object_3:
            current_drag_radius = ring_radius_3
        else:
            current_drag_radius = ring_radius_4

        max_x_bound = plane_length / 2 - current_drag_radius
        max_z_bound = plane_width / 2 - current_drag_radius

        new_x = max(-max_x_bound, min(max_x_bound, new_x))
        new_z = max(-max_z_bound, min(max_z_bound, new_z))

        dragging_object.pos.x = new_x
        dragging_object.pos.z = new_z


def on_mouseup(evt):
    """Handles mouse up events, releasing the dragged object."""
    global dragging_object
    dragging_object = None


scene.bind('mousedown', on_mousedown)
scene.bind('mousemove', on_mousemove)
scene.bind('mouseup', on_mouseup)


def on_keydown(evt):
    """Handles keyboard keydown events for various actions."""
    if evt.key == 'r' or evt.key == 'R':
        release_balls_action()
    elif evt.key == 'a' or evt.key == 'A':
        add_ball_action()
    elif evt.key == 'c' or evt.key == 'C':
        clear_all_balls_action()
    elif evt.key == 'v' or evt.key == 'V': # New shortcut 'V' to switch camera mode
        switch_camera_mode()


scene.bind('keydown', on_keydown)

# Create Ambisonics hemisphere
ambisonics_hemisphere = sphere(pos=hemisphere_center, radius=hemisphere_radius,
                               color=color.black, opacity=0.0, # Initially black and fully transparent
                               shininess=0.1, # Add some shininess
                               visible=True) # Ensure visibility

# Mark Azimuth 0, Elevation 0 point (prominently red)
# Azimuth 0, Elevation 0 typically corresponds to directly in front of the hemisphere center (positive Z-axis)
azimuth_elevation_zero_marker = sphere(pos=hemisphere_center + vector(0, 0, hemisphere_radius),
                                       radius=hemisphere_radius * 0.025,
                                       color=color.red,
                                       emissive=True, # Make it glow
                                       visible=True)
azimuth_elevation_zero_label = label(pos=azimuth_elevation_zero_marker.pos + vector(0, 0.5, 0),
                                     text='Ambisonics Zero (Front, Horizontal)',
                                     xoffset=0, yoffset=0, space=0, height=12,
                                     border=4, font='sans', box=False, color=color.white, visible=True)

# Pre-allocate spheres for each track
for track_num in track_numbers:
    # Create a single sphere for each track, initially visible
    s = sphere(radius=INDIVIDUAL_SOUND_SOURCE_RADIUS, color=color.white, emissive=True, opacity=0.1, visible=True)
    # Random angular velocity (visual effect is not obvious for spheres, but logic is retained)
    s.angular_velocity = vector(random.uniform(-1, 1), random.uniform(-1, 1),
                                random.uniform(-1, 1)).norm() * random.uniform(0.5, 2.0)
    s.current_scale = 1.0 # For pulse effect
    projected_sound_sources[track_num] = s # Store the single sphere object directly
    # Create the label once
    projected_sound_labels[track_num] = label(pos=hemisphere_center, text=str(track_num), xoffset=10, yoffset=10,
                                              space=0, height=12,
                                              border=4, font='sans', box=False, color=color.white, visible=True)

# New: Timer for periodically printing reaper_track_volumes
last_print_time = time.time()
PRINT_INTERVAL = 1.0 # Print once per second

while True:
    rate(100) # Run simulation at 100 frames per second
    current_sim_time = time.time()

    if event_phase == "normal":
        pass

    elif event_phase == "releasing":
        if not release_velocity_applied:
            # All balls are ejected
            all_balls_list = inner_balls + inner_balls_2 + inner_balls_3 + inner_balls_4
            for ball in all_balls_list:
                # Find the ring the ball belongs to
                if ball in inner_balls:
                    target_ring = rotating_object
                elif ball in inner_balls_2:
                    target_ring = rotating_object_2
                elif ball in inner_balls_3:
                    target_ring = rotating_object_3
                else:
                    target_ring = rotating_object_4

                direction_from_ring_center_xz = vector(ball.pos.x - target_ring.pos.x, 0,
                                                       ball.pos.z - target_ring.pos.z)
                if direction_from_ring_center_xz.mag == 0:
                    direction_from_ring_center_xz = vector(random.uniform(-1, 1), 0, random.uniform(-1, 1)).norm()
                else:
                    direction_from_ring_center_xz = direction_from_ring_center_xz.norm()
                ball.vel = direction_from_ring_center_xz * release_speed + vector(0, release_speed * 0.2, 0)
            release_velocity_applied = True

        # Reverb time is shared, reset event phase when it ends
        if reverb_active_time != -1.0:
            elapsed_since_reverb_active = current_sim_time - reverb_active_time
            if elapsed_since_reverb_active >= reverb_full_wet_duration + reverb_decay_duration:
                reverb_active_time = -1.0 # Reset reverb timer
                event_phase = "normal"
                last_event_trigger_time = current_sim_time
                print("Back to normal phase.")

    # Apply tilting to the ground and rings
    new_tilt_angle_x = max_tilt_angle_x * sin(t * tilt_frequency_x)
    incremental_tilt_angle_x = new_tilt_angle_x - previous_tilt_angle_x
    previous_tilt_angle_x = new_tilt_angle_x

    new_tilt_angle_z = max_tilt_angle_z * sin(t * tilt_frequency_z + tilt_phase_offset_z)
    incremental_tilt_angle_z = new_tilt_angle_z - previous_tilt_angle_z
    previous_tilt_angle_z = new_tilt_angle_z

    ground.rotate(angle=incremental_tilt_angle_x, axis=vector(1, 0, 0), origin=tilting_pivot_point)
    ground.rotate(angle=incremental_tilt_angle_z, axis=vector(0, 0, 1), origin=tilting_pivot_point)
    rotating_object.rotate(angle=incremental_tilt_angle_x, axis=vector(1, 0, 0), origin=tilting_pivot_point)
    rotating_object.rotate(angle=incremental_tilt_angle_z, axis=vector(0, 0, 1), origin=tilting_pivot_point)
    rotating_object_2.rotate(angle=incremental_tilt_angle_x, axis=vector(1, 0, 0), origin=tilting_pivot_point)
    rotating_object_2.rotate(angle=incremental_tilt_angle_z, axis=vector(0, 0, 1), origin=tilting_pivot_point)
    rotating_object_3.rotate(angle=incremental_tilt_angle_x, axis=vector(1, 0, 0), origin=tilting_pivot_point)
    rotating_object_3.rotate(angle=incremental_tilt_angle_z, axis=vector(0, 0, 1), origin=tilting_pivot_point)
    rotating_object_4.rotate(angle=incremental_tilt_angle_x, axis=vector(1, 0, 0), origin=tilting_pivot_point)
    rotating_object_4.rotate(angle=incremental_tilt_angle_z, axis=vector(0, 0, 1), origin=tilting_pivot_point)

    for ball in inner_balls + inner_balls_2 + inner_balls_3 + inner_balls_4:
        ball.rotate(angle=incremental_tilt_angle_x, axis=vector(1, 0, 0), origin=tilting_pivot_point)
        ball.rotate(angle=incremental_tilt_angle_z, axis=vector(0, 0, 1), origin=tilting_pivot_point)

    # Handle physics for each ring
    handle_ring_physics_for_object(rotating_object, ring_radius)
    handle_ring_physics_for_object(rotating_object_2, ring_radius_2)
    handle_ring_physics_for_object(rotating_object_3, ring_radius_3)
    handle_ring_physics_for_object(rotating_object_4, ring_radius_4)

    # Reset quadrant statistics for all rings (now only for shared tracks)
    for i in range(len(track_numbers)):
        quadrant_ball_stats[i]["count"] = 0
        quadrant_ball_stats[i]["total_speed"] = 0.0

    balls_to_add = []
    balls_to_remove = []

    # Process balls for the first ring
    for i, ball1 in enumerate(inner_balls):
        ball1.vel += g * dt
        apply_attraction_force_to_ball(ball1, rotating_object, ball_attraction_strength) # Apply attraction force
        ball1.pos += ball1.vel * dt

        handle_ball_ground_collision(ball1)
        handle_ball_ring_collision_for_object(ball1, rotating_object, ring_radius, ring_glow_obj, ring_vobj,
                                              current_sim_time, balls_to_add, balls_to_remove)

        relative_ball_pos_xz = vector(ball1.pos.x - rotating_object.pos.x, 0, ball1.pos.z - rotating_object.pos.z)
        if relative_ball_pos_xz.mag > 0.001:
            current_ball_angle_local = atan2(relative_ball_pos_xz.z, relative_ball_pos_xz.x)
            if current_ball_angle_local < 0:
                current_ball_angle_local += 2 * pi

            current_quadrant = int(current_ball_angle_local / section_angle_span)
            current_quadrant = min(current_quadrant, len(track_numbers) - 1)

            quadrant_ball_stats[current_quadrant]["count"] += 1
            quadrant_ball_stats[current_quadrant]["total_speed"] += ball1.vel.mag

        for j in range(i + 1, len(inner_balls)):
            ball2 = inner_balls[j]
            handle_ball_ball_collision(ball1, ball2, balls_to_add, balls_to_remove)

    # Process balls for the second ring
    for i, ball1 in enumerate(inner_balls_2):
        ball1.vel += g * dt
        apply_attraction_force_to_ball(ball1, rotating_object_2, ball_attraction_strength) # Apply attraction force
        ball1.pos += ball1.vel * dt

        handle_ball_ground_collision(ball1)
        handle_ball_ring_collision_for_object(ball1, rotating_object_2, ring_radius_2, ring_glow_obj_2, ring_vobj_2,
                                              current_sim_time, balls_to_add, balls_to_remove)

        relative_ball_pos_xz = vector(ball1.pos.x - rotating_object_2.pos.x, 0, ball1.pos.z - rotating_object_2.pos.z)
        if relative_ball_pos_xz.mag > 0.001:
            current_ball_angle_local = atan2(relative_ball_pos_xz.z, relative_ball_pos_xz.x)
            if current_ball_angle_local < 0:
                current_ball_angle_local += 2 * pi

            current_quadrant = int(current_ball_angle_local / section_angle_span)
            current_quadrant = min(current_quadrant, len(track_numbers) - 1)

            quadrant_ball_stats[current_quadrant]["count"] += 1
            quadrant_ball_stats[current_quadrant]["total_speed"] += ball1.vel.mag

        for j in range(i + 1, len(inner_balls_2)):
            ball2 = inner_balls_2[j]
            handle_ball_ball_collision(ball1, ball2, balls_to_add, balls_to_remove)

    # Process balls for the third ring
    for i, ball1 in enumerate(inner_balls_3):
        ball1.vel += g * dt
        apply_attraction_force_to_ball(ball1, rotating_object_3, ball_attraction_strength) # Apply attraction force
        ball1.pos += ball1.vel * dt

        handle_ball_ground_collision(ball1)
        handle_ball_ring_collision_for_object(ball1, rotating_object_3, ring_radius_3, ring_glow_obj_3, ring_vobj_3,
                                              current_sim_time, balls_to_add, balls_to_remove)

        relative_ball_pos_xz = vector(ball1.pos.x - rotating_object_3.pos.x, 0, ball1.pos.z - rotating_object_3.pos.z)
        if relative_ball_pos_xz.mag > 0.001:
            current_ball_angle_local = atan2(relative_ball_pos_xz.z, relative_ball_pos_xz.x)
            if current_ball_angle_local < 0:
                current_ball_angle_local += 2 * pi

            current_quadrant = int(current_ball_angle_local / section_angle_span)
            current_quadrant = min(current_quadrant, len(track_numbers) - 1)

            quadrant_ball_stats[current_quadrant]["count"] += 1
            quadrant_ball_stats[current_quadrant]["total_speed"] += ball1.vel.mag

        for j in range(i + 1, len(inner_balls_3)):
            ball2 = inner_balls_3[j]
            handle_ball_ball_collision(ball1, ball2, balls_to_add, balls_to_remove)

    # Process balls for the fourth ring
    for i, ball1 in enumerate(inner_balls_4):
        ball1.vel += g * dt
        apply_attraction_force_to_ball(ball1, rotating_object_4, ball_attraction_strength) # Apply attraction force
        ball1.pos += ball1.vel * dt

        handle_ball_ground_collision(ball1)
        handle_ball_ring_collision_for_object(ball1, rotating_object_4, ring_radius_4, ring_glow_obj_4, ring_vobj_4,
                                              current_sim_time, balls_to_add, balls_to_remove)

        relative_ball_pos_xz = vector(ball1.pos.x - rotating_object_4.pos.x, 0, ball1.pos.z - rotating_object_4.pos.z)
        if relative_ball_pos_xz.mag > 0.001:
            current_ball_angle_local = atan2(relative_ball_pos_xz.z, relative_ball_pos_xz.x)
            if current_ball_angle_local < 0:
                current_ball_angle_local += 2 * pi

            current_quadrant = int(current_ball_angle_local / section_angle_span)
            current_quadrant = min(current_quadrant, len(track_numbers) - 1)

            quadrant_ball_stats[current_quadrant]["count"] += 1
            quadrant_ball_stats[current_quadrant]["total_speed"] += ball1.vel.mag

        for j in range(i + 1, len(inner_balls_4)):
            ball2 = inner_balls_4[j]
            handle_ball_ball_collision(ball1, ball2, balls_to_add, balls_to_remove)

    # Update average speed and distance for all rings (now only for shared tracks)
    for i in range(len(track_numbers)):
        if quadrant_ball_stats[i]["count"] > 0:
            quadrant_ball_stats[i]["avg_speed"] = quadrant_ball_stats[i]["total_speed"] / quadrant_ball_stats[i][
                "count"]
        else:
            quadrant_ball_stats[i]["avg_speed"] = 0.0

    # OSC parameter update (now called once, handling shared track data)
    update_osc_parameters(current_sim_time)

    # Update inner_balls lists, removing balls marked for removal
    next_inner_balls = []
    for ball in inner_balls:
        if ball not in balls_to_remove:
            next_inner_balls.append(ball)
        else:
            ball.visible = False

    inner_balls = next_inner_balls

    next_inner_balls_2 = []
    for ball in inner_balls_2:
        if ball not in balls_to_remove:
            next_inner_balls_2.append(ball)
        else:
            ball.visible = False

    inner_balls_2 = next_inner_balls_2

    next_inner_balls_3 = []
    for ball in inner_balls_3:
        if ball not in balls_to_remove:
            next_inner_balls_3.append(ball)
        else:
            ball.visible = False

    inner_balls_3 = next_inner_balls_3

    next_inner_balls_4 = []
    for ball in inner_balls_4:
        if ball not in balls_to_remove:
            next_inner_balls_4.append(ball)
        else:
            ball.visible = False

    inner_balls_4 = next_inner_balls_4

    # Distribute newly created balls to random rings
    for b_add in balls_to_add:
        target_list = random.choice([inner_balls, inner_balls_2, inner_balls_3, inner_balls_4])
        if len(target_list) < MAX_BALLS: # Check against MAX_BALLS, not individual list capacity
            target_list.append(b_add)
        else:
            b_add.visible = False

    update_particles()

    # --- Ambisonics Hemisphere Visualization (Main Sphere Control) ---
    if reaper_play_status and not ambisonics_hemisphere_fade_active:
        # Calculate total volume of VPython internally controlled tracks (tracks 2-10)
        # The Ambisonics large sphere is now controlled by the volume generated from VPython's internal collision logic
        total_quadrant_volume = sum(quadrant_volumes)
        # Normalize total volume to 0-1 range for adjusting Ambisonics sphere brightness
        max_total_volume = len(track_numbers) * max_volume
        normalized_total_volume = total_quadrant_volume / max_total_volume if max_total_volume > 0 else 0

        # Control Ambisonics hemisphere brightness/opacity
        # Max opacity can be adjusted, e.g., 0.5 or 0.7 to make it more solid
        target_opacity = lerp(0.0, 0.5, normalized_total_volume)
        target_color = lerp(color.black, color.white, normalized_total_volume)

        ambisonics_hemisphere.opacity = lerp(ambisonics_hemisphere.opacity, target_opacity, 0.1) # Smooth transition
        ambisonics_hemisphere.color = lerp(ambisonics_hemisphere.color, target_color, 0.1) # Smooth transition

    elif ambisonics_hemisphere_fade_active:
        elapsed_fade_time = current_sim_time - ambisonics_hemisphere_fade_start_time
        if elapsed_fade_time < ambisonics_hemisphere_fade_duration:
            fade_progress = elapsed_fade_time / ambisonics_hemisphere_fade_duration
            ambisonics_hemisphere.opacity = lerp(ambisonics_hemisphere_initial_opacity, 0.0, fade_progress)
            ambisonics_hemisphere.color = lerp(ambisonics_hemisphere_initial_color, color.black, fade_progress)
        else:
            ambisonics_hemisphere.opacity = 0.0
            ambisonics_hemisphere.color = color.black
            ambisonics_hemisphere_fade_active = False
    else: # Initial state or fade-out complete, REAPER not playing
        ambisonics_hemisphere.opacity = 0.0
        ambisonics_hemisphere.color = color.black

    # Individual sound source spheres (tracks 2-10) visibility and appearance
    # Get volume of REAPER track 11 (still received and printed, but no longer affects large sphere)
    track_11_volume = reaper_track_volumes.get(11, 0.0)

    # Iterate through each track to update its corresponding projected sphere and label
    for i, track_num in enumerate(track_numbers):
        # Retrieve current Azimuth and Elevation values for this track
        # Azimuth and Elevation are still controlled by VPython's internal logic and sent to REAPER
        current_azimuth_norm = quadrant_azimuths[i]
        current_elevation_norm = quadrant_elevations[i]

        # Get the fader volume for this track, default to 0.0 if not yet received
        # Here, the actual fader volume received from REAPER is used to control the sphere's appearance
        fader_volume = reaper_track_volumes.get(track_num, 0.0)
        # Normalize fader volume for visualization (assuming REAPER sends 0-1 range)
        fader_normalized = max(0.0, min(1.0, fader_volume)) # Ensure value is between 0 and 1

        # Calculate effective brightness factor, now only affected by individual fader volume
        effective_brightness_factor = min(1.0, fader_normalized * 1.2)

        # Get the single sphere for this track
        s = projected_sound_sources[track_num]
        current_label = projected_sound_labels[track_num]

        # Always calculate position
        azimuth_angle = map_range(current_azimuth_norm, 0.0, 0.99, math.pi, -math.pi)
        elevation_angle = map_range(current_elevation_norm, 0.0, 1.0, 0.0, math.pi / 2)

        projected_x = hemisphere_radius * math.cos(elevation_angle) * math.sin(azimuth_angle)
        projected_y = hemisphere_radius * math.sin(elevation_angle)
        projected_z = hemisphere_radius * math.cos(elevation_angle) * math.cos(azimuth_angle)
        projected_pos = hemisphere_center + vector(projected_x, projected_y, projected_z)
        s.pos = projected_pos

        # Pulse effect: adjust size based on effective brightness intensity
        # When effective brightness is 0, target_scale is 1.0, sphere remains original size
        target_scale = 1.0 + effective_brightness_factor * 1.0 # Increase responsiveness to effective brightness
        s.current_scale = lerp(s.current_scale, target_scale, 0.1)
        s.radius = INDIVIDUAL_SOUND_SOURCE_RADIUS * s.current_scale

        # Color and opacity change based on effective brightness
        s.color = lerp(color.blue, color.white, effective_brightness_factor) # Color changes from blue to white with brightness
        # Opacity now smoothly transitions
        target_sphere_opacity = max(0.1, fader_normalized)
        s.opacity = lerp(s.opacity, target_sphere_opacity, 0.1)

        # Set emissive property based on effective brightness (e.g., if bright enough, it glows)
        s.emissive = effective_brightness_factor > 0.05

        # Apply rotation (visual effect is not obvious for spheres, but logic is retained)
        s.rotate(angle=s.angular_velocity.mag * dt, axis=s.angular_velocity.norm(), origin=s.pos)

        current_label.text = str(track_num)
        current_label.pos = projected_pos + vector(0.2, 0.2, 0.2) * s.current_scale
        current_label.color = color.white

        # Control sphere and label visibility based on REAPER play status
        # Modify this so that it's always visible when REAPER is playing, even if volume is 0 (but will be very dim)
        s.visible = reaper_play_status
        current_label.visible = reaper_play_status


    update_ring_visuals(current_sim_time)

    update_camera(current_sim_time)

    t += dt

    # Print REAPER received track volumes periodically
    if current_sim_time - last_print_time > PRINT_INTERVAL:
        print("\n--- REAPER Track Volume Status (Received) ---")
        # Print volumes for all received tracks
        for track_num in sorted(reaper_track_volumes.keys()):
            print(f"  Track {track_num}: {reaper_track_volumes[track_num]:.2f}")
        last_print_time = current_sim_time
