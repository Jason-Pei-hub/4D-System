# config.py
# 全局配置文件

# 网络配置
HOST = '0.0.0.0'
PORT_VIDEO = 8888      # OV9281
PORT_THERMAL = 8889    # Tiny1-C

# 分辨率参数
# Tiny1-C (基准分辨率)
THERMAL_W = 256
THERMAL_H = 192

# OV9281 (原始分辨率)
VIS_W = 1280
VIS_H = 800

# 标定板参数 (6x7 铜板)
CHECKERBOARD_SIZE = (6, 7)