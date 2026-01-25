import cv2
import numpy as np
import os
from config import VIS_W, VIS_H, THERMAL_W, THERMAL_H

class ImageAligner:
    def __init__(self):
        self.save_path = "matrix_tactical.npy"
        self.x = VIS_W // 2
        self.y = VIS_H // 2
        self.scale = 2.5
        self.angle = 0.0
        self.opacity = 0.5
        self.aspect = THERMAL_W / THERMAL_H
        self.load_params()

    def update_params(self, x=None, y=None, scale=None, angle=None, opacity=None):
        if x is not None: self.x = x
        if y is not None: self.y = y
        if scale is not None: self.scale = max(0.1, min(10.0, scale))
        if angle is not None: self.angle = angle
        if opacity is not None: self.opacity = max(0.1, min(1.0, opacity))
        self.save_params()

    def get_transform_params(self):
        w = int(THERMAL_W * self.scale)
        h = int(w / self.aspect)
        x = int(self.x - w / 2)
        y = int(self.y - h / 2)
        return x, y, w, h, self.angle, self.opacity

    def save_params(self):
        np.save(self.save_path, [self.x, self.y, self.scale, self.angle, self.opacity])

    def load_params(self):
        if os.path.exists(self.save_path):
            try:
                p = np.load(self.save_path)
                if len(p) == 5: self.x, self.y, self.scale, self.angle, self.opacity = p
                else: self.x, self.y, self.scale = p[:3]
            except: pass