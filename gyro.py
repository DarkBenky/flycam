import time

import board

import adafruit_mpu6050

i2c = board.I2C()
mpu = adafruit_mpu6050.MPU6050(i2c)

while True:
    print(
        f"Acceleration: X:{mpu.acceleration[0]:.2f}, Y: {mpu.acceleration[1]:.2f}, Z: {mpu.acceleration[2]:.2f} m/s^2"  # noqa: E501
    )
    print(f"Gyro X:{mpu.gyro[0]:.2f}, Y: {mpu.gyro[1]:.2f}, Z: {mpu.gyro[2]:.2f} rad/s")
    print(f"Temperature: {mpu.temperature:.2f} C")
    print("")
    time.sleep(0.1)
