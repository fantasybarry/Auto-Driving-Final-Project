# Auto Driving Final Project

'''
--Problem Statement:
Design a vehicle speed control and path following control to track the gps path below
(Target speed is 5 [mph]; Original data is attached).
Develop the controls in simulation using python for verification purpose.

--Original Data is attached:
Loyd_nobel_nav_rosbag2_2024_11_11-11_24_51.csv

--Latitude Column Names:
Latitude - deg
1deg of Latitude (Miles), 1deg of Latitude (Feet), 1deg of Latitude (Metres)
1' of Latitude (Miles), 1' of Latitude (Feet), 1' of Latitude (Metres)
1'' of Latitude (Miles), 1'' of Latitude (Feet), 1'' of Latitude (Metres)

--Longitude Column Names:
Longitude - deg
1deg of Longitude (Miles), 1deg of Longitude (Feet), 1deg of Longitude (Metres)
1' of Longitude (Miles), 1' of Longitude (Feet), 1' of Longitude (Metres)
1'' of Longitude (Miles), 1'' of Longitude (Feet), 1'' of Longitude (Metres)

--Test Data Column Names:
Time, Longitude, Latitude, Speed[mps], Brake_status

--TODO:
1. Make sure that the GPS data is being imported, processed, and followed correctly by the vehicle by the timestamps
    given in the test data.
2. Dynamic Models: Use more detailed vehicle dynamics models (e.g., dynamic bicycle model) that account for inertia,
   tire slip, and other real-world factors.
3. Multi-threading or Multiprocessing: Utilize parallel processing for computationally intensive tasks, such as
   path planning or sensor data processing.
'''

# Importing Required Libraries
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
from scipy.interpolate import interp1d
from scipy.constants import mile
from numba import njit, float64
from numba.experimental import jitclass
import cubic_spline_planner

k = 0.5   # Stanley control gain
Kp = 1.0  # PID control gain: P
Ki = 0.01 # PID control gain: I
Kd = 0.1  # PID control gain: D
dt = 0.1  # Time step
L = 2.7   # Wheel base of 2014 Nissan Leaf
max_steer = np.radians(30.0)
output_limit = 1.0

# Set to True to show the animation
show_animation = True

# Target speed in mph to m/s
TARGET_SPEED_MPH = 5.0
TARGET_SPEED_MPS = TARGET_SPEED_MPH * mile / 3600

# Define the state specification
state_spec = [
    ('x', float64),
    ('y', float64),
    ('yaw', float64),
    ('v', float64)
]

# Define the state class for the vehicle
@jitclass(state_spec)
class State:
    # Initialize the state of the vehicle
    def __init__(self, x, y, yaw, v):
        self.x = x
        self.y = y
        self.yaw = yaw
        self.v = v

    # Update the state of the vehicle
    def update(self, acceleration, delta):
        delta = min(max(delta, -max_steer), max_steer)
        self.x += self.v * np.cos(self.yaw) * dt
        self.y += self.v * np.sin(self.yaw) * dt
        self.yaw += self.v / L * np.tan(delta) * dt
        self.yaw = normalize_angle(self.yaw)
        self.v += acceleration * dt

# PID controller with Anti-Windup
@njit(cache=True)
def pid_control(target, current, prev_error=0.0, integral=0.0):
    # PID control gains
    error = target - current
    p_term = Kp * error
    integral += error * dt
    i_term = Ki * integral
    d_term = Kd * (error - prev_error) / dt
    output = p_term + i_term + d_term

    # Anti-Windup
    if output > output_limit:
        output = output_limit
        integral -= error * dt
    elif output < -output_limit:
        output = -output_limit
        integral -= error * dt

    return output, error, integral

# Function to normalize the angle
@njit(cache=True)
def normalize_angle(angle):
    return (angle + np.pi) % (2 * np.pi) - np.pi

# Function to calculate the target index
def calc_target_index(state, cx, cy, last_target_idx):
    fx, fy = state.x + L * np.cos(state.yaw), state.y + L * np.sin(state.yaw)
    dx, dy = cx[last_target_idx:] - fx, cy[last_target_idx:] - fy
    d = np.hypot(dx, dy)
    target_idx = np.argmin(d) + last_target_idx
    look_ahead_distance = k * state.v + 1.0

    # Check if the target index is out of bounds
    while target_idx + 1 < len(cx) and np.hypot(cx[target_idx + 1] - fx, cy[target_idx + 1] - fy) <= look_ahead_distance:
        target_idx += 1

    front_axle_vec = np.array([-np.cos(state.yaw + np.pi / 2), -np.sin(state.yaw + np.pi / 2)])
    error_front_axle = np.dot([fx - cx[target_idx], fy - cy[target_idx]], front_axle_vec)

    return target_idx, error_front_axle

# Stanley control function
def stanley_control(state, cx, cy, cyaw, last_target_idx):
    current_target_idx, error_front_axle = calc_target_index(state, cx, cy, last_target_idx)
    current_target_idx = max(last_target_idx, current_target_idx)
    theta_e = normalize_angle(cyaw[current_target_idx] - state.yaw)
    theta_d = np.arctan2(k * error_front_axle, state.v + 1e-5)
    delta = theta_e + theta_d

    return delta, current_target_idx

# Function to convert latitude and longitude to local x and y
def convert_to_local_x_y(test_data, lat_table, lon_table):
    lat_interp = interp1d(lat_table['Latitude - deg'], lat_table['1deg of Latitude (Metres)'], fill_value="extrapolate")
    latitude_meters_per_degree = lat_interp(test_data['Latitude'].values)
    latitude_meters = (test_data['Latitude'].values - test_data['Latitude'].values[0]) * latitude_meters_per_degree

    lon_interp = interp1d(lon_table['Latitude - deg'], lon_table['1deg of Longitude (Metres)'], fill_value="extrapolate")
    longitude_meters_per_degree = lon_interp(test_data['Latitude'].values)
    longitude_meters = (test_data['Longitude'].values - test_data['Longitude'].values[0]) * longitude_meters_per_degree

    return longitude_meters, latitude_meters

# Main function
def main():
    latitude_distance_to_latitude = pd.read_csv('latitude_distance_to_latitude.csv')
    longitude_distance_to_longitude = pd.read_csv('longitude_distance_to_longitude.csv')
    test_data_final = pd.read_csv('Loyd_nobel_nav_rosbag2_2024_11_11-11_24_51.csv')

    test_data_final['Local_X'], test_data_final['Local_Y'] = convert_to_local_x_y(
        test_data_final, latitude_distance_to_latitude, longitude_distance_to_longitude)
    test_data_final['Local_X'] -= test_data_final['Local_X'].iloc[0]
    test_data_final['Local_Y'] -= test_data_final['Local_Y'].iloc[0]
    test_data_final = test_data_final.drop_duplicates(subset=['Local_X', 'Local_Y']).reset_index(drop=True)

    # Kalman Filter for GPS data
    def kalman_filter(z, x_est, P_est, F, H, Q, R):
        # Prediction
        x_pred = F @ x_est
        P_pred = F @ P_est @ F.T + Q

        # Update
        y = z - H @ x_pred
        S = H @ P_pred @ H.T + R
        K = P_pred @ H.T @ np.linalg.inv(S)
        x_est = x_pred + K @ y
        P_est = (np.eye(len(K)) - K @ H) @ P_pred

        return x_est, P_est

    # Initialize Kalman Filter parameters
    F = np.eye(4)        # State transition matrix
    H = np.eye(4)        # Observation matrix
    Q = np.eye(4) * 0.1  # Process noise covariance
    R = np.eye(4) * 0.8  # Measurement noise covariance
    x_est = np.zeros(4)  # Initial state estimate
    P_est = np.eye(4)    # Initial estimate covariance

    # Apply Kalman Filter to the data
    filtered_data = []
    for i in range(len(test_data_final)):
        z = np.array([test_data_final['Local_X'].iloc[i], test_data_final['Local_Y'].iloc[i], 0, 0])
        x_est, P_est = kalman_filter(z, x_est, P_est, F, H, Q, R)
        filtered_data.append(x_est[:2])

    filtered_data = np.array(filtered_data)
    test_data_final['Filtered_X'] = filtered_data[:, 0]
    test_data_final['Filtered_Y'] = filtered_data[:, 1]

    # Plot the GPS trajectory
    plt.figure(figsize=(8, 8))
    size = 100
    plt.plot(test_data_final['Local_X'], test_data_final['Local_Y'], label='GPS Trajectory', color='r')
    plt.scatter(test_data_final['Local_X'].iloc[0], test_data_final['Local_Y'].iloc[0], marker='*',
                 color='g', s=size, label='Start')
    plt.scatter(test_data_final['Local_X'].iloc[-1], test_data_final['Local_Y'].iloc[-1], marker='<',
                 color='k', s=size, label='End')
    plt.xlabel('Local X (m)')
    plt.ylabel('Local Y (m)')
    plt.title('Local X and Y Trajectory')
    plt.axis('equal')
    plt.legend()
    plt.show()

    # Cubic Spline Path Planning
    cx, cy, cyaw, ck, s = cubic_spline_planner.calc_spline_course(
        test_data_final['Local_X'].tolist(), test_data_final['Local_Y'].tolist(), ds=0.1)

    # Path Tracking
    target_speed = TARGET_SPEED_MPS
    max_simulation_time = test_data_final['Time'].iloc[-1] - test_data_final['Time'].iloc[0]
    initial_x, initial_y = test_data_final['Local_X'].iloc[0], test_data_final['Local_Y'].iloc[0]
    dx_init, dy_init = test_data_final['Local_X'].iloc[1] - initial_x, test_data_final['Local_Y'].iloc[1] - initial_y
    initial_yaw = np.arctan2(dy_init, dx_init) + np.pi
    state = State(float(initial_x), float(initial_y), float(initial_yaw), 0.0)
    cx, cy, cyaw, ck = map(np.array, [cx, cy, cyaw, ck])

    # Simulation
    last_idx = len(cx) - 1
    time, n_steps = 0.0, int(max_simulation_time / dt) + 1
    x_history, y_history, yaw_history, v_history, t_history = [np.zeros(n_steps) for _ in range(5)]
    x_history[0], y_history[0], yaw_history[0], v_history[0], t_history[0] = state.x, state.y, state.yaw, state.v, time

    # Initial target index
    target_idx, _ = calc_target_index(state, cx, cy, 0)
    prev_error, integral = 0.0, 0.0

    # Simulation loop
    if show_animation:
        # Initial setting for visualization
        plt.figure(figsize=(8, 8))
        line_course, = plt.plot(cx, cy, ".r", label="Course")
        line_trajectory, = plt.plot([], [], "-b", label="Trajectory")
        point_target, = plt.plot([], [], "xg", label="Target")
        plt.scatter(cx[0], cy[0], marker='*', color='g', s=size, label='Start')
        plt.scatter(cx[-1], cy[-1], marker='<', color='k', s=size, label='End')
        plt.axis("equal")
        plt.xlabel("X [m]")
        plt.ylabel("Y [m]")
        plt.title("Path Tracking")
        plt.legend()
        plt.tight_layout()
        plt.show(block=False)
        plt.pause(0.1)

    i = 0
    while last_idx > target_idx:
        ai, new_error, new_integral = pid_control(target_speed, state.v, prev_error, integral)
        prev_error, integral = new_error, new_integral
        di, target_idx = stanley_control(state, cx, cy, cyaw, target_idx)
        state.update(ai, di)
        time += dt
        i += 1

        if i >= len(x_history):
            x_history, y_history, yaw_history, v_history, t_history = map(lambda arr: np.append(arr, np.zeros(100)),
                                                                           [x_history, y_history, yaw_history, v_history, t_history])

        x_history[i], y_history[i], yaw_history[i], v_history[i], t_history[i] = state.x, state.y, state.yaw, state.v, time

        if show_animation:
            line_trajectory.set_data(x_history[:i+1], y_history[:i+1])
            point_target.set_data([cx[target_idx]], [cy[target_idx]])
            plt.title(f"Speed [km/h]: {state.v * 3.6:.2f}")
            plt.pause(0.001)

    # Truncate the arrays
    x_history, y_history, yaw_history, v_history, t_history = map(lambda arr: arr[:i+1],
                                                                   [x_history, y_history, yaw_history, v_history, t_history])

    # Print the simulation results
    print("Goal reached!" if last_idx <= target_idx else "Goal not reached within the simulation time.")

    if show_animation:
        plt.figure(figsize=(10, 5))

        plt.subplot(1, 2, 1)
        plt.scatter(cx[0], cy[0], marker='*', color='g', s=size, label='Start')
        plt.scatter(cx[-1], cy[-1], marker='<', color='k', s=size, label='End')
        plt.plot(cx, cy, ".r", label="Course")
        
        plt.plot(x_history, y_history, "-b", label="Trajectory")
        plt.xlabel("X [m]")
        plt.ylabel("Y [m]")
        plt.title("Path Tracking")
        plt.axis("equal")
        plt.legend()

        plt.subplot(1, 2, 2)
        plt.plot(t_history, v_history * 3.6, "-r")
        plt.xlabel("Time [s]")
        plt.ylabel("Speed [km/h]")
        plt.title("Speed Profile")
        plt.tight_layout()
        plt.show()

if __name__ == '__main__':
     main()
