from vpython import *
import math
import time
from pythonosc import udp_client
import random

# --- OSC (Open Sound Control) Configuration ---
reaper_ip = "172.20.10.5"  # REAPER 所在的 IP 地址
reaper_port = 8000  # REAPER 監聽的 UDP 端口

client = udp_client.SimpleUDPClient(reaper_ip, reaper_port)

# Define track numbers for individual ball hits
track_numbers = [1, 2, 3, 4, 5, 6, 7, 8, 9]  # 9 tracks for 9 quadrants

# Master track for global effects (e.g., reverb)
master_track_number = 10  # Assuming a master track or a dedicated FX track in REAPER

# --- Sound Control Parameters ---
max_volume = 0.7  # 最大音量
decay_time = 0.3  # 音量衰減時間 (秒)

# Pitch parameters (example: -1.0 to 1.0 might map to -12 to +12 semitones in REAPER)
max_pitch_bend = 0.5  # Max pitch shift (e.g., 0.5 for half an octave up/down)
pitch_sensitivity = 0.1  # How much ball speed affects pitch

# Pan parameters (-1.0 for full left, 1.0 for full right, 0.0 for center)
pan_range = 1.0  # Max pan value from center

# Master FX parameters (example values, adjust based on REAPER plugin ranges)
master_reverb_drywet_on = 0.8  # Reverb amount during release burst
master_reverb_drywet_off = 0.0  # Reverb amount when off

# New: Reverb decay specific parameters for release phase
reverb_active_time = -1.0  # Tracks when reverb effect was activated (for full wet duration)
reverb_full_wet_duration = 1.0  # Duration (in seconds) for which reverb stays at master_reverb_drywet_on
reverb_decay_duration = 1.0  # Duration (in seconds) of reverb decay after full wet duration

# Initialize decay timers and volumes for each quadrant
quadrant_decay_timers = [-1] * len(track_numbers)
quadrant_volumes = [0.0] * len(track_numbers)

# Initialize other OSC parameters for each quadrant
quadrant_pitches = [0.0] * len(track_numbers)
quadrant_pans = [0.0] * len(track_numbers)

last_hit_quadrant = -1  # Not strictly used, but kept for consistency if needed


# --- OSC Send Function ---
def send_osc_message(address, value):
    """Generic function to send an OSC message."""
    try:
        client.send_message(address, float(value))
        # print(f"Sent OSC: {address} {value:.2f}") # For debugging
    except Exception as e:
        print(f"Error sending OSC message to {address} with value {value}: {e}")


# Initial OSC setup: ensure all tracks are at 0 volume and default pitch/pan
for i in range(len(track_numbers)):
    send_osc_message(f"/track/{track_numbers[i]}/volume", 0.0)
    send_osc_message(f"/track/{track_numbers[i]}/pitch", 0.0)  # Reset pitch
    send_osc_message(f"/track/{track_numbers[i]}/pan", 0.0)  # Reset pan

# Reset master effects: Ensure master reverb is off at start
send_osc_message(f"/track/{master_track_number}/reverb/drywet", master_reverb_drywet_off)

time.sleep(0.1)  # Give REAPER a moment to process initial messages

# --- VPython Scene Setup ---
scene.center = vector(0, 0, 0)
scene.autoscale = False
scene.range = 5
scene.width = 1200
scene.height = 800
scene.background = color.black  # 將背景設為黑色，讓環更突出

# Define time step
dt = 0.005  # Smaller time step for higher simulation precision
t = 0  # Time variable for controlling tilt animation

# --- Physics Parameters ---
g = vector(0, -30, 0)  # Gravity acceleration
plane_cor = 0.6  # Coefficient of restitution for plane collision (elasticity), determines bounce height
friction_coefficient_plane = 0.15  # Friction coefficient for plane, controls sliding resistance

# --- Plane ---
plane_length = 8 * 2  # 平台長度 (已變為兩倍)
plane_width = 8 * 2  # 平台寬度 (已變為兩倍)
plane_thickness = 0.1
plane_color = color.cyan
plane_opacity = .1  # Plane opacity set to 0 (已修改)

# Create ground object. Its position will be world coordinate (0,0,0).
ground = box(pos=vector(0, 0, 0), length=plane_length, height=plane_thickness, width=plane_width,
             color=plane_color, opacity=plane_opacity)

ground_y_top_world = ground.pos.y + plane_thickness / 2

ring_radius = 2 * 2  # 環半徑 (已變為兩倍)
ring_thickness = 0.1  # Ring thickness
ring_base_color = color.white  # 環的基礎顏色
ring_color = ring_base_color  # Ring color (initial color) (已修改為白色)

# --- Ring Glow/Color Change Parameters ---
ring_glow_color = color.white  # 環發光的目標顏色
ring_glow_opacity = 0.0  # 環發光的當前不透明度
ring_glow_fade_speed = 5.0  # 環發光衰減速度
ring_glow_obj = ring(pos=vector(0, 0, 0),
                     radius=ring_radius,
                     thickness=ring_thickness * 1.5,  # 讓發光體稍微厚一點，形成光暈效果
                     color=ring_glow_color,
                     axis=vector(0, 1, 0),
                     opacity=ring_glow_opacity)

quadrant_colors = [
    vector(1, 0, 0),  # 紅色 (Red)
    vector(0, 1, 0),  # 綠色 (Green)
    vector(0, 0, 1),  # 藍色 (Blue)
    vector(1, 1, 0),  # 黃色 (Yellow)
    vector(0, 1, 1),  # 青色 (Cyan)
    vector(1, 0, 1),  # 洋紅色 (Magenta)
    vector(1, 0.5, 0),  # 橘色 (Orange)
    vector(0.5, 0, 0.5),  # 紫色 (Purple)
    vector(1, 1, 1)  # 白色 (White)
]

dot_radius = 0.2  # Dot radius, adjusted to a larger value for better observation
dot_color = color.yellow  # Dot color (已修改為黃色)

ring_y_pos_world = ground_y_top_world + ring_thickness / 2

# Create ring object. Its position is relative to the compound's center (0,0,0)
ring_vobj = ring(pos=vector(0, 0, 0),  # Relative to compound center
                 radius=ring_radius,
                 thickness=ring_thickness,
                 color=ring_color,
                 axis=vector(0, 1, 0),  # Initially flat
                 opacity=0.7)  # Ring opacity set to 0.7 (已修改)

dot_offset_from_ring_edge = 0.5  # Adjust this value to control how far it floats outside
# Create dot object. Its position is relative to the compound's center (0,0,0)
dot_vobj = sphere(pos=vector(ring_radius + dot_offset_from_ring_edge, 0, 0),  # Relative to compound center
                  radius=dot_radius,
                  color=dot_color,
                  opacity=0.5)  # Dot opacity set to 0.5 (已修改)

rotating_object = compound([ring_vobj, dot_vobj, ring_glow_obj], pos=vector(0, ring_y_pos_world, 0))

rotating_object.vel = vector(1.5, 0, 1.0)

rotating_object.angular_vel = vector(0, 2.5, 0)  # radians/second

constant_torque_magnitude = 0.025  # Adjust this value to control the "thrust" of self-rotation, preventing it from stopping

initial_inner_ball_radius = (0.3 / 2) / 2  # 初始球半徑再減半
# Define colors for each of the nine sections when the ball hits it
ball_quadrant_colors = [
    vector(0.5, 0, 0),  # 深紅色 (DarkRed)
    vector(0, 0.5, 0),  # 深綠色 (DarkGreen)
    vector(0, 0, 0.5),  # 深藍色 (DarkBlue)
    vector(1, 0.84, 0),  # 金色 (Gold)
    vector(0.88, 1, 1),  # 淺青色 (LightCyan)
    vector(1, 0.75, 0.8),  # 粉紅色 (Pink)
    vector(0.65, 0.16, 0.16),  # 棕色 (Brown)
    vector(0.58, 0.44, 0.86),  # 中紫色 (MediumPurple)
    vector(0.8, 0.8, 0.8)  # 淺灰色 (LightGray)
]

inner_ball_cor = 0.8  # 內球與地面及環的恢復係數
inner_ball_friction = 0.1  # 內球與地面及環的摩擦係數

# List to hold all inner ball objects
inner_balls = []
MAX_BALLS = 200  # Maximum number of balls allowed in the simulation
MAX_SPLIT_EVENTS_PER_BALL = 1  # Each ball can cause 1 split
MIN_BALL_RADIUS = 0.02  # Minimum radius for a ball to be created (still useful if initial_inner_ball_radius changes)

# Cooldown to prevent a single ball from splitting multiple times in quick succession
SPLIT_COOLDOWN = 0.5  # seconds

# New: Dictionary to track contact duration between balls
ball_contact_timers = {}
PROLONGED_CONTACT_THRESHOLD = 0.5  # seconds
RAPID_SEPARATION_SPEED = 10.0  # Speed at which balls separate after prolonged contact

# New: Dictionary to track prolonged contact with the ring
ring_contact_timers = {}
PROLONGED_RING_CONTACT_THRESHOLD = 0.1  # seconds (Changed from 1.0 to 0.1)
RING_SEPARATION_SPEED = 10.0  # Speed at which balls separate from the ring (Increased from 3.0 to 10.0)

ring_normal_indicator = cylinder(pos=rotating_object.pos,
                                 axis=rotating_object.up.norm() * 1.0,  # 長度為 1.0，可以調整
                                 radius=0.05,  # 圓柱體半徑
                                 color=color.red,  # 法線顏色
                                 opacity=0.8)

attraction_duration = 2.5  # 吸引持續 1.5 秒
attraction_strength = 10  # 吸引力強度 (可調整)
damping_strength = 5.0  # 阻尼係數 (可調整)
release_speed = 30.0  # 釋放時的速度 (可調整)

# New repulsion parameters for "反彈力道會越大"
repulsion_threshold = 0.5  # 距離法線中心小於此值時開始產生排斥力
repulsion_max_strength = 20.0  # 在法線中心點的最大排斥力

ring_hit_count = 0  # 初始化環撞擊計數
hits_to_trigger_event = 300  # 觸發吸引事件所需的撞擊次數
ready_to_attract_time = -1.0  # 記錄撞擊次數達到閾值的時間，-1.0 表示未達到或已處理
attraction_delay = 0.1  # 撞擊次數達到後，延遲 0.1 秒開始吸引

last_event_trigger_time = time.time()
event_phase = "normal"  # "normal", "attracting", "releasing"


# --- Particle System Parameters ---
class Particle:
    def __init__(self, pos, vel, radius, color, lifespan):
        self.vobj = sphere(pos=pos, radius=radius, color=color, opacity=1.0, emissive=True)  # Emissive for glow
        self.vel = vel
        self.lifespan = lifespan
        self.creation_time = time.time()
        self.initial_opacity = 1.0


particles = []  # List to hold active particles

# --- Camera Shake Parameters ---
camera_shake_active = False
shake_start_time = 0
shake_duration = 0.2  # 震動持續時間
shake_intensity = 0.05  # 震動強度 (每次位移的最大值)
last_shake_trigger_hit_count = 0  # 上次觸發震動的撞擊次數

# --- Camera Tracking Parameters ---
camera_tracking_speed = 0.05  # 攝影機追蹤平滑度
fixed_camera_offset = vector(0, 5, 5)  # 預設攝影機相對於目標的偏移
fixed_look_at_offset = vector(0, -5, -5)  # 預設攝影機看向目標的偏移


# --- Helper function for linear interpolation (lerp) ---
def lerp(start, end, t_val):
    """
    Performs linear interpolation between two vectors or numbers.
    t_val should be between 0 and 1.
    """
    return start * (1 - t_val) + end * t_val


def create_new_ball(current_pos=None, current_vel=None, radius=None, collision_normal=None):
    """
    Creates a new inner ball with specified properties.
    If current_pos is None, it's an initial ball.
    If current_pos is not None, it's a split ball.
    """
    initial_pos = vector(0, 0, 0)
    initial_vel = vector(0, 0, 0)
    current_ball_radius = radius if radius is not None else initial_inner_ball_radius

    if current_pos is None:  # For initial ball creation
        max_spawn_offset = ring_radius - current_ball_radius - ring_thickness / 2 - 0.1
        rand_x = (random.random() * 2 - 1) * max_spawn_offset
        rand_z = (random.random() * 2 - 1) * max_spawn_offset
        initial_pos = vector(rand_x, ground_y_top_world + current_ball_radius + 0.01, rand_z)

        base_speed = 0.5  # A moderate initial speed

        dist_pos_x = (plane_length / 2) - initial_pos.x
        dist_neg_x = initial_pos.x - (-plane_length / 2)
        dist_pos_z = (plane_width / 2) - initial_pos.z
        dist_neg_z = initial_pos.z - (-plane_width / 2)

        min_dist_x = min(abs(dist_pos_x), abs(dist_neg_x))
        min_dist_z = min(abs(dist_pos_z), abs(dist_neg_z))

        if min_dist_x < min_dist_z:  # X wall is closer
            if abs(dist_pos_x) == min_dist_x:  # Closer to positive X wall
                initial_vel.x = -base_speed
            else:  # Closer to negative X wall
                initial_vel.x = base_speed
            initial_vel.z = (random.random() * 2 - 1) * 0.1  # Small random Z component
        else:  # Z wall is closer or equal distance
            if abs(dist_pos_z) == min_dist_z:  # Closer to positive Z wall
                initial_vel.z = -base_speed
            else:  # Closer to negative Z wall
                initial_vel.z = base_speed
            initial_vel.x = (random.random() * 2 - 1) * 0.1  # Small random X component

        # Add a small random component to avoid perfectly straight lines and make it more dynamic
        initial_vel.x += random.uniform(-0.05, 0.05)
        initial_vel.z += random.uniform(-0.05, 0.05)

    else:  # For splitting (current_pos is not None)
        # Small random offset for new balls to avoid immediate re-collision
        offset_vec = vector(random.uniform(-0.1, 0.1), 0, random.uniform(-0.1, 0.1))
        initial_pos = current_pos + offset_vec

        speed = max(current_vel.mag, 1)  # Ensure minimum speed for split balls (set to 1)

        temp_new_ball_dir = vector(random.uniform(-1, 1), 0, random.uniform(-1, 1)).hat  # Start with a random direction

        if collision_normal is not None:  # Only apply if there was a collision normal (from the ring wall hit)
            if dot(temp_new_ball_dir, collision_normal) < 0:
                temp_new_ball_dir = temp_new_ball_dir - 2 * dot(temp_new_ball_dir, collision_normal) * collision_normal

        if temp_new_ball_dir.mag == 0:
            # If it becomes a zero vector, give a completely random direction as fallback
            temp_new_ball_dir = vector(random.uniform(-1, 1), 0, random.uniform(-1, 1)).hat

        initial_vel = temp_new_ball_dir.hat * speed  # Normalize and multiply by speed
        initial_vel.y = current_vel.y  # Keep original vertical velocity

    new_ball = sphere(pos=initial_pos,
                      radius=current_ball_radius,  # Use the passed radius
                      color=color.yellow)  # Default color for new balls
    new_ball.vel = initial_vel
    new_ball.times_split = 0  # Crucial: new children start with 0 splits caused
    new_ball.last_split_time = time.time()  # Set initial cooldown for new balls
    return new_ball


inner_balls.append(create_new_ball(radius=initial_inner_ball_radius))

tilting_pivot_point = vector(0, ground.pos.y - plane_thickness / 2, 0)  # World coordinate

# --- Tilting Parameters ---
max_tilt_angle_x = radians(15)  # 圍繞 X 軸的最大傾斜角度 (15 度)
tilt_frequency_x = 0.8  # 圍繞 X 軸的傾斜擺動速度 (每秒循環次數)

max_tilt_angle_z = radians(10)  # 新增：圍繞 Z 軸的最大傾斜角度 (10 度)
tilt_frequency_z = 0.6  # 新增：圍繞 Z 軸的傾斜擺動速度 (每秒循環次數)
tilt_phase_offset_z = math.pi / 2  # 新增：Z 軸傾斜的相位偏移，使其與 X 軸錯開

# 設定攝影機視角 (初始值，會被追蹤邏輯覆蓋)
scene.camera.pos = vector(0, 5, 5)
scene.camera.axis = vector(0, -5, -5)

# 用於追蹤傾斜的當前角度。
previous_tilt_angle_x = 0  # 追蹤上一個時間步圍繞 X 軸的傾斜角度
previous_tilt_angle_z = 0  # 新增：追蹤上一個時間步圍圍繞 Z 軸的傾斜角度

section_angle_span = (2 * pi) / 9


# --- VPython UI Elements ---
# Sliders for Tilt Control
def set_tilt_x(s):
    global max_tilt_angle_x
    max_tilt_angle_x = radians(s.value)


scene.append_to_caption('\n最大 X 軸傾斜角度 (度): ')
tilt_x_slider = slider(min=0, max=30, value=degrees(max_tilt_angle_x), step=1, bind=set_tilt_x)
scene.append_to_caption(' ')


def set_tilt_z(s):
    global max_tilt_angle_z
    max_tilt_angle_z = radians(s.value)


scene.append_to_caption('最大 Z 軸傾斜角度 (度): ')
tilt_z_slider = slider(min=0, max=30, value=degrees(max_tilt_angle_z), step=1, bind=set_tilt_z)
scene.append_to_caption('\n')


# Sliders for Physics Parameters
def set_gravity(s):
    global g
    g.y = -s.value


scene.append_to_caption('重力強度: ')
gravity_slider = slider(min=10, max=50, value=abs(g.y), step=1, bind=set_gravity)
scene.append_to_caption(' ')


def set_friction(s):
    global friction_coefficient_plane, inner_ball_friction
    friction_coefficient_plane = s.value
    inner_ball_friction = s.value  # Apply to both for simplicity


scene.append_to_caption('摩擦係數: ')
friction_slider = slider(min=0, max=0.5, value=friction_coefficient_plane, step=0.01, bind=set_friction)
scene.append_to_caption('\n')


def set_attraction_strength(s):
    global attraction_strength
    attraction_strength = s.value


scene.append_to_caption('吸引力強度: ')
attraction_slider = slider(min=1, max=50, value=attraction_strength, step=1, bind=set_attraction_strength)
scene.append_to_caption(' ')


def set_decay_time(s):
    global decay_time
    decay_time = s.value


scene.append_to_caption('音量衰減時間 (秒): ')
decay_time_slider = slider(min=0.1, max=1.0, value=decay_time, step=0.05, bind=set_decay_time)
scene.append_to_caption('\n')


# Buttons for Ball Control
def add_ball_action():
    if len(inner_balls) < MAX_BALLS:
        inner_balls.append(create_new_ball(radius=initial_inner_ball_radius))


scene.append_to_caption(' ')
button(text='新增小球', bind=add_ball_action)
scene.append_to_caption(' ')


def clear_all_balls_action():
    global inner_balls, particles, ring_hit_count
    for ball in inner_balls:
        ball.visible = False
    inner_balls = []
    for p in particles:
        p.vobj.visible = False
    particles = []
    ring_hit_count = 0  # Reset hit count
    print("所有小球和粒子已清除。")


scene.append_to_caption(' ')
button(text='清除所有小球', bind=clear_all_balls_action)
scene.append_to_caption('\n')


# Buttons for REAPER Transport Control
def reaper_play_action():
    send_osc_message("/play", 1)  # Send 1 to trigger play
    print("REAPER: 播放")


scene.append_to_caption(' ')
button(text='REAPER 播放', bind=reaper_play_action)
scene.append_to_caption(' ')


def reaper_stop_action():
    send_osc_message("/stop", 1)  # Send 1 to trigger stop
    print("REAPER: 停止")


scene.append_to_caption(' ')
button(text='REAPER 停止', bind=reaper_stop_action)
scene.append_to_caption('\n')


# Marker trigger (for testing, could be tied to other events)
def trigger_marker_action(marker_num):
    send_osc_message(f"/marker/{marker_num}/play", 1)
    print(f"REAPER: 觸發 Marker {marker_num}")


# --- Helper Functions for Main Loop ---

def apply_collision_response(obj_vel, normal, cor, friction_coeff, dt, mass=1.0):
    """
    Applies collision response (restitution and friction) to an object's velocity.
    Args:
        obj_vel (vector): Current velocity of the object.
        normal (vector): Normal vector of the collision surface.
        cor (float): Coefficient of restitution.
        friction_coeff (float): Coefficient of friction.
        dt (float): Time step.
        mass (float): Mass of the object (used for friction, default to 1.0 if not provided).
    Returns:
        vector: Updated velocity after collision response.
    """
    v_normal = dot(obj_vel, normal) * normal
    v_tangent = obj_vel - v_normal

    v_normal_after_bounce = -v_normal * cor

    if v_tangent.mag > 0:
        # Simplified normal force for friction calculation (assuming gravity is the primary source)
        # More accurate would involve impulse, but for a general helper, this approximation works.
        normal_force_magnitude = g.mag * mass  # Assuming mass is 1 for VPython spheres
        friction_magnitude = friction_coeff * normal_force_magnitude
        friction_acceleration_vector = -v_tangent.norm() * friction_magnitude * dt

        if friction_acceleration_vector.mag >= v_tangent.mag:
            v_tangent = vector(0, 0, 0)
        else:
            v_tangent += friction_acceleration_vector

    return v_normal_after_bounce + v_tangent


def update_osc_parameters(current_time):
    """Updates and decays OSC parameters for each quadrant."""
    global quadrant_volumes, quadrant_decay_timers, reverb_active_time

    # Master Reverb Decay Logic
    if reverb_active_time != -1.0:
        elapsed_since_reverb_active = current_time - reverb_active_time

        if elapsed_since_reverb_active < reverb_full_wet_duration:
            current_reverb_wet = master_reverb_drywet_on
        elif elapsed_since_reverb_active < reverb_full_wet_duration + reverb_decay_duration:
            decay_progress = (elapsed_since_reverb_active - reverb_full_wet_duration) / reverb_decay_duration
            current_reverb_wet = master_reverb_drywet_on * (1 - decay_progress)
        else:
            current_reverb_wet = master_reverb_drywet_off
            reverb_active_time = -1.0  # Reset timer

        send_osc_message(f"/track/{master_track_number}/reverb/drywet", current_reverb_wet)

    # Individual Quadrant Volume Decay
    for i in range(len(track_numbers)):
        if quadrant_decay_timers[i] != -1:
            elapsed_time = current_time - quadrant_decay_timers[i]
            if elapsed_time < decay_time:
                decay_factor = 1 - (elapsed_time / decay_time)
                new_volume = max_volume * decay_factor
                quadrant_volumes[i] = max(0, new_volume)  # Ensure volume doesn't go below 0
                send_osc_message(f"/track/{track_numbers[i]}/volume", quadrant_volumes[i])
            else:
                if quadrant_volumes[i] > 0:
                    quadrant_volumes[i] = 0.0
                    send_osc_message(f"/track/{track_numbers[i]}/volume", quadrant_volumes[i])
                quadrant_decay_timers[i] = -1


def update_ring_visuals():
    """Manages the ring's glow and color fading."""
    global ring_glow_opacity, ring_glow_obj, ring_vobj

    if ring_glow_opacity > 0:
        ring_glow_opacity -= ring_glow_fade_speed * dt
        if ring_glow_opacity < 0: ring_glow_opacity = 0
        ring_glow_obj.opacity = ring_glow_opacity

    # Fade main ring color back to base color
    ring_vobj.color = ring_vobj.color * (1 - ring_glow_fade_speed * dt) + ring_base_color * (ring_glow_fade_speed * dt)
    # Ensure color components don't go below 0 or above 1
    ring_vobj.color = vector(max(0, min(1, ring_vobj.color.x)),
                             max(0, min(1, ring_vobj.color.y)),
                             max(0, min(1, ring_vobj.color.z)))

    # Update background light effect
    max_active_volume = 0.0
    for vol in quadrant_volumes:
        max_active_volume = max(max_active_volume, vol)

    base_bg_color = color.black
    vibrant_bg_color = color.white
    current_bg_intensity = max_active_volume * 2.0
    current_bg_intensity = min(current_bg_intensity, 1.0)

    scene.background = base_bg_color * (1 - current_bg_intensity) + vibrant_bg_color * current_bg_intensity


def update_camera(current_time):
    """Handles camera shake and smooth tracking."""
    global camera_shake_active, shake_start_time

    # Camera Shake Logic
    if camera_shake_active:
        elapsed_shake_time = current_time - shake_start_time
        if elapsed_shake_time < shake_duration:
            current_shake_intensity = shake_intensity * (1 - elapsed_shake_time / shake_duration)
            scene.camera.pos += vector(random.uniform(-1, 1), random.uniform(-1, 1),
                                       random.uniform(-1, 1)).norm() * current_shake_intensity
            scene.camera.axis += vector(random.uniform(-1, 1), random.uniform(-1, 1),
                                        random.uniform(-1, 1)).norm() * current_shake_intensity * 0.5
        else:
            camera_shake_active = False

    # Camera Tracking Logic
    target_camera_pos = rotating_object.pos + fixed_camera_offset
    target_look_at_pos = rotating_object.pos + fixed_look_at_offset

    if event_phase == "attracting":
        target_camera_pos = rotating_object.pos + vector(0, 7, 3)
        target_look_at_pos = rotating_object.pos + vector(0, 0, 0)
    elif event_phase == "releasing":
        target_camera_pos = rotating_object.pos + vector(0, 8, 8)
        target_look_at_pos = rotating_object.pos + vector(0, -2, -2)

    scene.camera.pos = lerp(scene.camera.pos, target_camera_pos, camera_tracking_speed)
    scene.camera.axis = lerp(scene.camera.axis, target_look_at_pos - scene.camera.pos, camera_tracking_speed)


def handle_ring_physics():
    """Updates the rotating object's (ring+dot) physics and handles ground collision."""
    rotating_object.vel += g * dt
    rotating_object.pos += rotating_object.vel * dt

    rotating_object.angular_vel += rotating_object.up.norm() * constant_torque_magnitude * dt
    rotating_object.rotate(angle=rotating_object.angular_vel.mag * dt,
                           axis=rotating_object.angular_vel.norm(),
                           origin=rotating_object.pos)

    ground_normal = ground.up.norm()
    distance_center_to_plane_top = dot(rotating_object.pos - (ground.pos + (plane_thickness / 2) * ground_normal),
                                       ground_normal)
    min_distance_for_no_penetration = ring_thickness / 2

    # Collision detection and position correction with ground
    if distance_center_to_plane_top < min_distance_for_no_penetration:
        projection_on_plane_top = rotating_object.pos - distance_center_to_plane_top * ground_normal
        rotating_object.pos = projection_on_plane_top + min_distance_for_no_penetration * ground_normal

        if dot(rotating_object.vel, ground_normal) < 0:  # Only apply if moving downwards
            rotating_object.vel = apply_collision_response(rotating_object.vel, ground_normal, 0.0,
                                                           friction_coefficient_plane, dt)  # COR 0 for sticking

    # Boundary checks for the ring on the plane
    ground_local_x_axis = ground.axis.norm()
    ground_local_z_axis = cross(ground_normal, ground_local_x_axis).norm()

    vec_ring_to_ground_center = rotating_object.pos - ground.pos
    local_x = dot(vec_ring_to_ground_center, ground_local_x_axis)
    local_z = dot(vec_ring_to_ground_center, ground_local_z_axis)

    max_x_bound = plane_length / 2 - ring_radius
    max_z_bound = plane_width / 2 - ring_radius

    if abs(local_x) > max_x_bound:
        clamped_x = max_x_bound * sign(local_x)
        correction_vec_x = (clamped_x - local_x) * ground_local_x_axis
        rotating_object.pos += correction_vec_x
        rotating_object.vel -= 2 * dot(rotating_object.vel, ground_local_x_axis) * ground_local_x_axis * 0.5

    if abs(local_z) > max_z_bound:
        clamped_z = max_z_bound * sign(local_z)
        correction_vec_z = (clamped_z - local_z) * ground_local_z_axis
        rotating_object.pos += correction_vec_z
        rotating_object.vel -= 2 * dot(rotating_object.vel, ground_local_z_axis) * ground_local_z_axis * 0.5

    ring_normal_indicator.pos = rotating_object.pos
    ring_normal_indicator.axis = rotating_object.up.norm() * 1.0


def handle_ball_ground_collision(ball):
    """Handles collision between an inner ball and the ground."""
    ground_normal = ground.up.norm()
    distance_ball_to_plane_top = dot(ball.pos - (ground.pos + (plane_thickness / 2) * ground_normal),
                                     ground_normal)

    if distance_ball_to_plane_top < ball.radius and dot(ball.vel, ground_normal) < 0:
        projection_on_plane_top_ball = ball.pos - distance_ball_to_plane_top * ground_normal
        ball.pos = projection_on_plane_top_ball + ball.radius * ground_normal

        ball.vel = apply_collision_response(ball.vel, ground_normal, inner_ball_cor, inner_ball_friction, dt)


def handle_ball_ring_collision(ball, current_time, balls_to_add, balls_to_remove):
    """Handles collision between an inner ball and the rotating ring."""
    global ring_hit_count, camera_shake_active, shake_start_time, last_shake_trigger_hit_count, ring_glow_color, ring_glow_opacity

    vec_ball_to_ring_center_xz = vector(ball.pos.x - rotating_object.pos.x, 0,
                                        ball.pos.z - rotating_object.pos.z)
    ball_horizontal_dist = vec_ball_to_ring_center_xz.mag

    ring_inner_radius_effective = ring_radius - ring_thickness / 2

    if ball_horizontal_dist > ring_inner_radius_effective - ball.radius:
        collision_normal_xz = vec_ball_to_ring_center_xz.norm()
        penetration_depth = (ball_horizontal_dist + ball.radius) - ring_inner_radius_effective
        ball.pos -= penetration_depth * vector(collision_normal_xz.x, 0, collision_normal_xz.z)

        if event_phase == "normal":
            ring_hit_count += 1
            if ring_hit_count % 50 == 0 and ring_hit_count != last_shake_trigger_hit_count:
                camera_shake_active = True
                shake_start_time = current_time
                last_shake_trigger_hit_count = ring_hit_count

        # Prolonged contact with ring
        if id(ball) not in ring_contact_timers:
            ring_contact_timers[id(ball)] = current_time
        else:
            contact_duration = current_time - ring_contact_timers[id(ball)]
            if contact_duration > PROLONGED_RING_CONTACT_THRESHOLD:
                separation_direction = -collision_normal_xz
                ball.vel = separation_direction * RING_SEPARATION_SPEED
                ring_contact_timers.pop(id(ball), None)
                return  # Skip normal collision resolution for this frame

        # Apply collision response
        ball_vel_xz = vector(ball.vel.x, 0, ball.vel.z)
        ball.vel = vector(
            apply_collision_response(ball_vel_xz, collision_normal_xz, inner_ball_cor, inner_ball_friction, dt).x,
            ball.vel.y,
            apply_collision_response(ball_vel_xz, collision_normal_xz, inner_ball_cor, inner_ball_friction, dt).z)

        # OSC Trigger and Volume Control
        relative_ball_pos = ball.pos - rotating_object.pos
        ring_local_up_axis = rotating_object.axis.norm()
        temp_ref = vector(1, 0, 0) if abs(dot(ring_local_up_axis, vector(1, 0, 0))) < 0.9 else vector(0, 0, 1)
        ring_local_right_axis = cross(ring_local_up_axis, temp_ref).norm()
        ring_local_forward_axis = cross(ring_local_right_axis, ring_local_up_axis).norm()

        local_x_component = dot(relative_ball_pos, ring_local_right_axis)
        local_z_component = dot(relative_ball_pos, ring_local_forward_axis)

        collision_angle_local = atan2(local_z_component, local_x_component)
        if collision_angle_local < 0:
            collision_angle_local += 2 * pi

        hit_quadrant = int(collision_angle_local / section_angle_span)
        hit_quadrant = min(hit_quadrant, len(track_numbers) - 1)

        # Volume control
        quadrant_volumes[hit_quadrant] = max_volume
        quadrant_decay_timers[hit_quadrant] = time.time()
        send_osc_message(f"/track/{track_numbers[hit_quadrant]}/volume", quadrant_volumes[hit_quadrant])

        # Pitch control
        normalized_speed = min(ball.vel.mag / 20.0, 1.0)
        pitch_val = normalized_speed * max_pitch_bend * 2 - max_pitch_bend
        quadrant_pitches[hit_quadrant] = pitch_val
        send_osc_message(f"/track/{track_numbers[hit_quadrant]}/pitch", quadrant_pitches[hit_quadrant])

        # Pan control
        normalized_pan_pos = local_x_component / ring_radius
        pan_val = normalized_pan_pos * pan_range
        quadrant_pans[hit_quadrant] = pan_val
        send_osc_message(f"/track/{track_numbers[hit_quadrant]}/pan", quadrant_pans[hit_quadrant])

        ball.color = ball_quadrant_colors[hit_quadrant]

        # Ring Glow/Color Change Trigger
        ring_glow_color = ball_quadrant_colors[hit_quadrant]
        ring_glow_opacity = min(ball.vel.mag / 20.0, 1.0)
        ring_glow_obj.color = ring_glow_color
        ring_glow_obj.opacity = ring_glow_opacity
        ring_vobj.color = ring_glow_color

        # Ball splitting logic
        if ball.times_split < MAX_SPLIT_EVENTS_PER_BALL and \
                len(inner_balls) + len(balls_to_add) < MAX_BALLS and \
                (time.time() - ball.last_split_time > SPLIT_COOLDOWN):

            new_child_radius = ball.radius
            if new_child_radius >= MIN_BALL_RADIUS:
                ball.times_split += 1
                balls_to_remove.append(ball)

                for _ in range(3):
                    new_ball = create_new_ball(ball.pos, ball.vel, new_child_radius, collision_normal_xz)
                    balls_to_add.append(new_ball)
                    # Particle Effect on Split
                    for _ in range(5):
                        p_vel = vector(random.uniform(-1, 1), random.uniform(-1, 1),
                                       random.uniform(-1, 1)).norm() * random.uniform(2, 5)
                        particles.append(Particle(new_ball.pos, p_vel, random.uniform(0.01, 0.03), new_ball.color,
                                                  random.uniform(0.3, 0.6)))
    else:
        if id(ball) in ring_contact_timers:
            ring_contact_timers.pop(id(ball), None)


def handle_ball_ball_collision(ball1, ball2, balls_to_add, balls_to_remove):
    """Handles collision between two inner balls."""
    # Ensure both balls are not marked for removal
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

        ball1.pos += normal * (overlap / 2 + 0.001)
        ball2.pos -= normal * (overlap / 2 + 0.001)

        rv = ball2.vel - ball1.vel
        vel_along_normal = dot(rv, normal)

        if vel_along_normal > 0:
            return

        impulse_scalar = -(1 + inner_ball_cor) * vel_along_normal / 2
        impulse = impulse_scalar * normal

        ball1.vel -= impulse
        ball2.vel += impulse

        # Particle Effect on Ball-Ball Collision
        if impulse_scalar > 0.5:
            for _ in range(3):
                p_vel = vector(random.uniform(-1, 1), random.uniform(-1, 1),
                               random.uniform(-1, 1)).norm() * random.uniform(1, 3)
                particles.append(Particle((ball1.pos + ball2.pos) / 2, p_vel, random.uniform(0.01, 0.02),
                                          (ball1.color + ball2.color) / 2, random.uniform(0.2, 0.4)))
    else:
        if contact_key in ball_contact_timers:
            ball_contact_timers.pop(contact_key, None)


def update_particles():
    """Updates the position and opacity of active particles."""
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


# --- Main Simulation Loop ---
while True:
    rate(100)  # Update 100 times per second
    current_sim_time = time.time()

    # --- Event Logic (Attraction/Release) ---
    # Removed the 'global' keyword here as these variables are already global.
    # event_phase, ready_to_attract_time, last_event_trigger_time, ring_hit_count, camera_shake_active, shake_start_time, reverb_active_time

    if event_phase == "normal":
        if ring_hit_count >= hits_to_trigger_event and ready_to_attract_time == -1.0:
            ready_to_attract_time = current_sim_time
            print(f"達到 {hits_to_trigger_event} 次撞擊，將在 {attraction_delay} 秒後開始吸引。")
            camera_shake_active = True
            shake_start_time = current_sim_time
            trigger_marker_action(1)

        if ready_to_attract_time != -1.0 and (current_sim_time - ready_to_attract_time) >= attraction_delay:
            event_phase = "attracting"
            last_event_trigger_time = current_sim_time
            ready_to_attract_time = -1.0
            print("開始吸引階段！")

    elif event_phase == "attracting":
        if current_sim_time - last_event_trigger_time < attraction_duration:
            for ball in inner_balls:
                horizontal_vec_to_center = vector(rotating_object.pos.x - ball.pos.x, 0,
                                                  rotating_object.pos.z - ball.pos.z)
                horizontal_distance = horizontal_vec_to_center.mag
                total_force = vector(0, 0, 0)

                normalized_distance_attraction = min(horizontal_distance / ring_radius, 1.0)
                current_attraction_strength_scaled = attraction_strength * normalized_distance_attraction * 1.2

                if horizontal_distance > 0:
                    attraction_direction = horizontal_vec_to_center.norm()
                    total_force += attraction_direction * current_attraction_strength_scaled

                attraction_force_vertical = rotating_object.up.norm() * attraction_strength * 0.2
                total_force += attraction_force_vertical

                ball_vel_horizontal = vector(ball.vel.x, 0, ball.vel.z)
                if horizontal_distance > 0 and ball_vel_horizontal.mag > 0:
                    direction_ball_to_center = horizontal_vec_to_center.norm()
                    velocity_towards_center = dot(ball_vel_horizontal, direction_ball_to_center)

                    if velocity_towards_center > 0:
                        normalized_distance_damping = min(horizontal_distance / ring_radius, 1.0)
                        damping_factor = 1.0 - normalized_distance_damping
                        damping_force = -direction_ball_to_center * velocity_towards_center * damping_strength * damping_factor
                        total_force += damping_force

                if horizontal_distance < repulsion_threshold and horizontal_distance > 0:
                    repulsion_factor = 1.0 - (horizontal_distance / repulsion_threshold)
                    repulsion_direction = -horizontal_vec_to_center.norm()
                    repulsion_force = repulsion_direction * repulsion_max_strength * repulsion_factor * 1.5
                    total_force += repulsion_force

                ball.vel += total_force * dt
        else:
            event_phase = "releasing"
            last_event_trigger_time = current_sim_time
            print("開始釋放階段！")
            camera_shake_active = True
            shake_start_time = current_sim_time
            send_osc_message(f"/track/{master_track_number}/reverb/drywet", master_reverb_drywet_on)
            reverb_active_time = current_sim_time
            trigger_marker_action(2)

            for ball in inner_balls:
                direction_from_ring_center_xz = vector(ball.pos.x - rotating_object.pos.x, 0,
                                                       ball.pos.z - rotating_object.pos.z)
                if direction_from_ring_center_xz.mag == 0:
                    direction_from_ring_center_xz = vector(random.uniform(-1, 1), 0, random.uniform(-1, 1)).norm()
                else:
                    direction_from_ring_center_xz = direction_from_ring_center_xz.norm()
                ball.vel = direction_from_ring_center_xz * release_speed + vector(0, release_speed * 0.2, 0)

    elif event_phase == "releasing":
        if reverb_active_time == -1.0:
            event_phase = "normal"
            ring_hit_count = 0
            last_event_trigger_time = current_sim_time
            print("回到正常階段，撞擊計數已重置。")

    # --- Tilting Application ---
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

    for ball in inner_balls:
        ball.rotate(angle=incremental_tilt_angle_x, axis=vector(1, 0, 0), origin=tilting_pivot_point)
        ball.rotate(angle=incremental_tilt_angle_z, axis=vector(0, 0, 1), origin=tilting_pivot_point)

    # --- Handle Ring Physics ---
    handle_ring_physics()

    # --- Handle Inner Balls Physics and Collisions ---
    balls_to_add = []
    balls_to_remove = []

    for i, ball1 in enumerate(inner_balls):
        ball1.vel += g * dt
        ball1.pos += ball1.vel * dt

        handle_ball_ground_collision(ball1)
        handle_ball_ring_collision(ball1, current_sim_time, balls_to_add, balls_to_remove)

        for j in range(i + 1, len(inner_balls)):
            ball2 = inner_balls[j]
            handle_ball_ball_collision(ball1, ball2, balls_to_add, balls_to_remove)

    # Update inner_balls list after processing all collisions
    next_inner_balls = []
    for ball in inner_balls:
        if ball not in balls_to_remove:
            next_inner_balls.append(ball)
        else:
            ball.visible = False

    for b_add in balls_to_add:
        if len(next_inner_balls) < MAX_BALLS:
            next_inner_balls.append(b_add)
        else:
            b_add.visible = False

    inner_balls = next_inner_balls

    # --- Update Particles ---
    update_particles()

    # --- Update Ring Visuals (Glow and Background) ---
    update_ring_visuals()

    # --- Update Camera ---
    update_camera(current_sim_time)

    # --- Update OSC Parameters (Volume Decay) ---
    update_osc_parameters(current_sim_time)

    t += dt  # Update time for tilt animation
