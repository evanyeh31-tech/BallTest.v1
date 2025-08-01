from vpython import *
import random
import math

# --- 場景與基本設定 ---
scene.center = vector(0, 0, 0)
scene.autoscale = False
scene.range = 5
scene.width = 1000
scene.height = 800

# 增加環境光和光源
scene.ambient = color.gray(0.3)
distant_light(direction=vector(1, 1, 1), color=color.white)
distant_light(direction=vector(-1, -1, -1), color=color.gray(0.5))

# --- 物理參數 ---
side_length = 4
thickness = 0.1
wall_height = 0.2
initial_sphere_radius = 0.2  # 初始球體半徑
dt = 0.005  # 時間步長

friction_coefficient = 0.05  # 底部摩擦係數
wall_cor = {
    "front": 0.9,
    "back": 0.7,
    "left": 0.5,
    "right": 0.9
}

# 初始射出速度的變數 (現在由滑桿控制)
initial_launch_speed_value = 2.5

# 計算內部活動空間的邊界
inner_boundary = (side_length / 2) - thickness

# --- 盒子組件創建 ---
# 底座：黑色，透明度 0.5
box(pos=vector(0, 0, 0), length=side_length, height=thickness, width=side_length,
    color=color.black, opacity=0.5)

# 計算牆壁的 Y 位置和內部維度
wall_y_pos = (thickness / 2) + (wall_height / 2)
inner_dimension = side_length - 2 * thickness

# 定義牆壁參數 (方向向量, 長度軸, 寬度軸, 初始顏色, 反彈係數)
wall_configs = [
    (vector(0, 0, side_length / 2 - thickness / 2), inner_dimension, thickness, color.white, wall_cor["front"]),
    # Front (+Z)
    (vector(0, 0, -(side_length / 2 - thickness / 2)), inner_dimension, thickness, color.white, wall_cor["back"]),
    # Back (-Z)
    (vector(-(side_length / 2 - thickness / 2), 0, 0), thickness, inner_dimension, color.white, wall_cor["left"]),
    # Left (-X)
    (vector(side_length / 2 - thickness / 2, 0, 0), thickness, inner_dimension, color.white, wall_cor["right"])
    # Right (+X)
]

walls = {}
wall_bounce_factors = {}
wall_names = ["front", "back", "left", "right"]

for i, (pos, length, width, col, bounce_factor) in enumerate(wall_configs):
    name = wall_names[i]
    if name in ["front", "back"]:  # Z方向的牆壁
        walls[name] = box(pos=vector(pos.x, wall_y_pos, pos.z), length=length, height=wall_height, width=width,
                          color=col, opacity=0.8)
    else:  # X方向的牆壁
        walls[name] = box(pos=vector(pos.x, wall_y_pos, pos.z), length=length, height=wall_height, width=width,
                          color=col, opacity=0.8)
    wall_bounce_factors[name] = bounce_factor

# --- 球體設定 ---
# 修改：現在我們有一個球的列表，而不是單一個球
# 每個元素將是一個字典，包含 'obj' (VPython sphere), 'vel' (velocity), 'radius' (current radius)
# 'generation' (for tracking recursive creation), 'color_inc' (for independent color changes)
balls = []
# sphere_pos_y 變數已不再需要，因為Y位置將根據當前半徑動態計算

# --- 新增的球體生成參數 ---
MAX_GENERATION = 2  # 只有世代為 0 或 1 的球才能生成新的球 (generation < 2)
MAX_TOTAL_BALLS = 1000  # 最大球體數量，防止過多球導致性能下降
GENERATION_COOLDOWN = 0.2  # 新生成的球體可以再次生成下一代的冷卻時間 (秒)

# --- 初始速度與運行狀態 ---
running = False  # 程式一開始是暫停狀態
t = 0  # 初始化時間變數

# --- 用戶設定 UI 控件 ---
scene.append_to_caption("\n\n")  # 增加一些空間


# 更新箭頭方向的函數 (現在需要從滑桿獲取位置)
# 提前定義，因為滑桿的bind會用到它
def update_direction_arrow(angle_degrees):
    # 確保箭頭位置跟隨滑桿的X和Z值更新
    # 箭頭的Y位置應與初始球體貼合底座的Y位置相同
    direction_arrow.pos = vector(pos_x_slider.value, thickness / 2 + initial_sphere_radius, pos_z_slider.value)
    angle_radians = math.radians(angle_degrees)
    direction_vec = vector(math.cos(angle_radians), 0, math.sin(angle_radians)).hat
    direction_arrow.axis = direction_vec * initial_sphere_radius * 3


# 初始位置 X 座標滑桿
scene.append_to_caption("Initial Ball X Position: ")
pos_x_slider = slider(min=-inner_boundary + initial_sphere_radius, max=inner_boundary - initial_sphere_radius,
                      value=0, step=0.01,
                      bind=lambda s: update_direction_arrow(angle_slider.value))
scene.append_to_caption("\n")

# 初始位置 Z 座標滑桿
scene.append_to_caption("Initial Ball Z Position: ")
pos_z_slider = slider(min=-inner_boundary + initial_sphere_radius, max=inner_boundary - initial_sphere_radius,
                      value=0, step=0.01,
                      bind=lambda s: update_direction_arrow(angle_slider.value))
scene.append_to_caption("\n")

# 初始方向角度滑桿 (使用角度，0-360度)
scene.append_to_caption("Initial Launch Angle (degrees from +X axis): ")
angle_slider = slider(min=0, max=360, value=0, step=1,
                      bind=lambda s: update_direction_arrow(s.value))
scene.append_to_caption("\n")

# 視覺化初始方向的箭頭
# 箭頭的pos要隨球體位置移動，axis根據角度
direction_arrow = arrow(pos=vector(pos_x_slider.value, thickness / 2 + initial_sphere_radius, pos_z_slider.value),
                        axis=vector(1, 0, 0) * initial_sphere_radius * 3,
                        color=color.cyan, shaftwidth=0.05)

# 初始化箭頭
update_direction_arrow(angle_slider.value)

# 初始射出速度滑桿
scene.append_to_caption("Initial Launch Speed: ")


def set_initial_launch_speed_slider(s):
    global initial_launch_speed_value
    initial_launch_speed_value = s.value


initial_speed_slider = slider(min=0.5, max=5.0, value=initial_launch_speed_value, step=0.1,
                              bind=set_initial_launch_speed_slider)
scene.append_to_caption("\n")

# --- 預先創建第一個球體，使其在啟動時可見 ---
# 創建第一個球，其Y位置直接根據其半徑和底座厚度計算
first_ball_obj = sphere(pos=vector(0, thickness / 2 + initial_sphere_radius, 0), radius=initial_sphere_radius,
                        color=color.red)
balls.append({
    'obj': first_ball_obj,
    'vel': vector(0, 0, 0),  # 初始速度為0，靜止
    'radius': initial_sphere_radius,
    'generation': 0,  # 第一個球是第0代
    'can_generate_next_at_time': 0,  # 初始球可以立即生成，因為 t 從 0 開始
    'color_inc': {'r': 0.001, 'g': 0.002, 'b': 0.0015},  # 初始變色參數
    'color_val': {'r': 1.0, 'g': 0.0, 'b': 0.0}  # 將初始顏色值設為紅色，確保可見
})


# --- 開始模擬按鈕 ---
def start_simulation_action(b):
    global running

    # 隱藏設定用的 UI 控件
    pos_x_slider.visible = False
    pos_z_slider.visible = False
    angle_slider.visible = False
    direction_arrow.visible = False
    initial_speed_slider.visible = False
    b.visible = False  # 隱藏「開始模擬」按鈕本身

    # 根據滑桿的最終設定來初始化第一個球體的速度和位置
    # 現在不再創建新球，而是更新已存在的第一個球
    if balls:  # 確保balls列表不為空
        first_ball_data = balls[0]
        # 更新位置，確保Y位置根據當前半徑正確貼合底座
        first_ball_data['obj'].pos = vector(pos_x_slider.value, thickness / 2 + first_ball_data['radius'],
                                            pos_z_slider.value)
        final_angle_radians = math.radians(angle_slider.value)
        final_direction_vec = vector(math.cos(final_angle_radians), 0, math.sin(final_angle_radians)).hat
        first_ball_data['vel'] = final_direction_vec * initial_launch_speed_value
        first_ball_data['obj'].color = color.red  # 重新設定顏色，確保開始時是紅色
        first_ball_data['can_generate_next_at_time'] = t  # 確保開始時可以生成

    running = True  # 設定為運行狀態，開始模擬


start_button = button(text="Start Simulation", bind=start_simulation_action)
scene.append_to_caption("\n\n")


# 綁定給 PlayPause 按鈕的回調函數
def toggle_play_pause(b):
    global running
    running = not running
    b.text = "Play" if not running else "Pause"


play_pause_button = button(text="Pause", bind=toggle_play_pause)
scene.append_to_caption(" ")

# --- 場景視角設定 ---
scene.camera.pos = vector(0, side_length * 1.5, side_length * 1.5)
scene.camera.axis = vector(0, -side_length * 1.5, -side_length * 1.5)

# --- 模擬循環 ---
while True:
    rate(200)

    # 更新時間
    if running:  # 只有在模擬運行時才更新時間
        t += dt

    # 在設定階段，即使不運行物理，也要確保箭頭位置更新
    # 確保球體位置變化時，箭頭也跟著移動
    if not running:
        update_direction_arrow(angle_slider.value)
        # 在非運行狀態下，確保第一個球的位置與滑桿同步
        if balls:
            balls[0]['obj'].pos.x = pos_x_slider.value
            balls[0]['obj'].pos.z = pos_z_slider.value
            # 確保Y位置根據當前半徑正確貼合底座
            balls[0]['obj'].pos.y = thickness / 2 + balls[0]['radius']

    # 處理所有球體的變色邏輯
    for ball_data in balls:
        rChan = ball_data['color_val']['r']
        gChan = ball_data['color_val']['g']
        bChan = ball_data['color_val']['b']
        rInc = ball_data['color_inc']['r']
        gInc = ball_data['color_inc']['g']
        bInc = ball_data['color_inc']['b']

        rChan += rInc
        gChan += gInc
        bChan += bInc

        if rChan >= 1 or rChan <= 0:
            rInc *= -1
            rChan = max(0.0, min(1.0, rChan))
        if gChan >= 1 or gChan <= 0:
            gInc *= -1
            gChan = max(0.0, min(1.0, gChan))
        if bChan >= 1 or bChan <= 0:
            bInc *= -1
            bChan = max(0.0, min(1.0, bChan))

        ball_data['obj'].color = vector(rChan, gChan, bChan)
        ball_data['color_val'] = {'r': rChan, 'g': gChan, 'b': bChan}
        ball_data['color_inc'] = {'r': rInc, 'g': gInc, 'b': bInc}

    if running:
        new_balls_to_add = []  # 用於暫存新生成的球，避免在迭代時修改列表

        # 迭代所有球體進行物理更新
        # 使用一個副本進行迭代，以便在循環中安全地從原始列表中刪除
        current_balls = list(balls)
        for ball_data in current_balls:
            # 檢查球是否已經被移除（例如，因為它已經停止並被清理）
            if not ball_data['obj'].visible:
                continue

            ball_obj = ball_data['obj']
            ball_vel = ball_data['vel']
            ball_radius = ball_data['radius']
            ball_gen = ball_data['generation']  # 獲取球的世代
            can_generate_next_at_time = ball_data['can_generate_next_at_time']  # 獲取生成冷卻時間

            # --- 應用摩擦力 ---
            current_ball_speed = ball_vel.mag
            if current_ball_speed > 0:
                # 計算摩擦力造成的速度變化
                friction_deceleration = friction_coefficient * ball_vel.hat * dt

                # 更新速度，但確保不會因為摩擦力而反向
                if friction_deceleration.mag >= current_ball_speed:  # 如果摩擦力足以讓球停下
                    ball_vel = vector(0, 0, 0)  # 球停下
                else:
                    ball_vel -= friction_deceleration

            # 更新球體位置
            ball_obj.pos += ball_vel * dt

            # --- 碰撞檢測與反彈應用 ---
            # 使用旗標來追蹤當前幀是否發生了任何碰撞
            collided_this_frame = False
            wall_normals_hit = []  # 儲存當前幀撞擊的牆壁法線

            # 暫存碰撞後的速度分量
            new_vel_x = ball_vel.x
            new_vel_z = ball_vel.z

            # Z軸碰撞檢測
            if ball_obj.pos.z + ball_radius > inner_boundary:  # 前牆 (+Z)
                new_vel_z *= -wall_bounce_factors["front"]
                ball_obj.pos.z = inner_boundary - ball_radius
                collided_this_frame = True
                wall_normals_hit.append(vector(0, 0, 1))  # 記錄法線
            elif ball_obj.pos.z - ball_radius < -inner_boundary:  # 後牆 (-Z)
                new_vel_z *= -wall_bounce_factors["back"]
                ball_obj.pos.z = -inner_boundary + ball_radius
                collided_this_frame = True
                wall_normals_hit.append(vector(0, 0, -1))  # 記錄法線

            # X軸碰撞檢測
            if ball_obj.pos.x + ball_radius > inner_boundary:  # 右牆 (+X)
                new_vel_x *= -wall_bounce_factors["right"]
                ball_obj.pos.x = inner_boundary - ball_radius
                collided_this_frame = True
                wall_normals_hit.append(vector(1, 0, 0))  # 記錄法線
            elif ball_obj.pos.x - ball_radius < -inner_boundary:  # 左牆 (-X)
                new_vel_x *= -wall_bounce_factors["left"]
                ball_obj.pos.x = -inner_boundary + ball_radius
                collided_this_frame = True
                wall_normals_hit.append(vector(-1, 0, 0))  # 記錄法線

            # 將碰撞後的速度分量應用回球體速度
            ball_vel.x = new_vel_x
            ball_vel.z = new_vel_z

            # --- 球體生成邏輯 (僅在當前幀發生碰撞時執行一次) ---
            # 只有世代為 0 或 1 的球才能生成新的球 (generation < MAX_GENERATION)
            # 並且需要通過冷卻時間檢查
            if collided_this_frame and ball_gen < MAX_GENERATION and t >= can_generate_next_at_time:  # 使用 t 變數
                # 確保總球數未超過上限
                if len(balls) + len(new_balls_to_add) < MAX_TOTAL_BALLS:
                    current_speed = ball_vel.mag  # 碰撞後的速度大小
                    new_radius = ball_radius / 2  # 新球半徑減半
                    if new_radius > 0.02:  # 設置最小半徑，避免球太小
                        for _ in range(3):  # 每次碰撞生成三顆新球 (已修改為3)
                            # 隨機方向 (X-Z 平面)
                            random_angle = random.uniform(0, 2 * math.pi)
                            random_direction = vector(math.cos(random_angle), 0, math.sin(random_angle)).hat

                            # 強制新球方向不會撞向剛才的牆壁
                            # 遍歷所有撞擊的牆壁法線，確保新方向遠離這些牆壁
                            temp_new_ball_dir = random_direction
                            for normal in wall_normals_hit:
                                # 如果隨機方向指向牆內，則沿法線方向翻轉
                                if dot(temp_new_ball_dir, normal) < 0:
                                    temp_new_ball_dir = temp_new_ball_dir - 2 * dot(temp_new_ball_dir, normal) * normal

                            # 確保調整後的方向向量不是零向量，避免除以零錯誤
                            if temp_new_ball_dir.mag == 0:
                                # 如果變成零向量，給一個完全隨機的方向作為備用
                                temp_new_ball_dir = vector(random.uniform(-1, 1), 0, random.uniform(-1, 1)).hat

                            new_ball_vel = temp_new_ball_dir.hat * current_speed  # 正規化並乘以速度

                            # 稍微偏移新球的位置，確保它們在牆壁外
                            # 偏移量應考慮新球半徑和一個小緩衝
                            # 這裡使用父球的當前位置加上新球速度方向的偏移
                            # 加上一個小緩衝 (0.01) 確保新球不會緊貼牆壁
                            offset_pos = ball_obj.pos + new_ball_vel.hat * (ball_radius + new_radius + 0.01)
                            offset_pos.y = thickness / 2 + new_radius  # 新球的Y位置也要調整

                            new_ball_obj = sphere(pos=offset_pos, radius=new_radius, color=color.white)
                            new_balls_to_add.append({
                                'obj': new_ball_obj,
                                'vel': new_ball_vel,
                                'radius': new_radius,
                                'generation': ball_gen + 1,  # 新生成的球世代加1
                                'can_generate_next_at_time': t + GENERATION_COOLDOWN,  # 設定新球的冷卻時間，使用 t 變數
                                'color_inc': {'r': random.uniform(0.0005, 0.002), 'g': random.uniform(0.0005, 0.002),
                                              'b': random.uniform(0.0005, 0.002)},
                                'color_val': {'r': random.random(), 'g': random.random(), 'b': random.random()}
                            })
                # 如果生成了新球，更新當前球的冷卻時間，防止同一幀再次生成
                ball_data['can_generate_next_at_time'] = t + GENERATION_COOLDOWN  # 使用 t 變數

            # 確保球體停留在底座上方 (無垂直彈跳)
            ball_data['obj'].pos.y = thickness / 2 + ball_data['radius']

            # 更新球體的速度 (因為可能在碰撞中改變)
            ball_data['vel'] = ball_vel

        # 將新生成的球添加到主列表中
        balls.extend(new_balls_to_add)
        # 清理停止移動且半徑過小的球（可選，用於性能優化）
        balls_to_remove = []
        for i, ball_data in enumerate(balls):
            # 如果球的速度極低（接近停止）且半徑小於某個閾值，則移除它
            # 這裡的清理閾值應該基於最小可能生成的球的半徑。
            # 由於 MAX_GENERATION = 2，最小球的半徑是 initial_sphere_radius / (2^2) = initial_sphere_radius / 4 = 0.2 / 4 = 0.05
            # 所以 0.02 仍然是一個合理的清理閾值。
            if ball_data['vel'].mag < 0.01 and ball_data['radius'] < 0.02:  # 設置一個絕對的最小半徑閾值
                ball_data['obj'].visible = False  # 隱藏球體
                ball_data['obj'].delete()  # 從VPython場景中刪除球體對象
                balls_to_remove.append(i)

        # 從後往前刪除，避免索引問題
        for i in sorted(balls_to_remove, reverse=True):
            del balls[i]
