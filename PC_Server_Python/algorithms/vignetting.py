# algorithms/vignetting.py
import numpy as np
import cv2
from config import VIS_W, VIS_H


class VignettingCorrector:
    def __init__(self, strength=0.8):
        """
        基于多项式拟合的平场校正 (Flat-Field Correction)
        公式: I_corr = I_raw * G(r)
        """
        self.gain_map = self._create_gain_map(VIS_W, VIS_H, strength)

    def _create_gain_map(self, w, h, k):
        # 生成坐标网格
        X, Y = np.meshgrid(np.arange(w), np.arange(h))
        cx, cy = w // 2, h // 2

        # 计算归一化半径 r (中心为0，角落为1)
        max_dist = np.sqrt(cx ** 2 + cy ** 2)
        r = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2) / max_dist

        # 增益函数: 越靠边，增益越大
        # 这里使用简化的二次模型 G = 1 + k*r^2
        gain = 1 + k * (r ** 2)
        return gain.astype(np.float32)

    def process(self, img):
        if img is None: return None
        # 转换类型进行计算: uint8 -> float32 -> uint8
        img_f = img.astype(np.float32)
        res = img_f * self.gain_map
        return np.clip(res, 0, 255).astype(np.uint8)