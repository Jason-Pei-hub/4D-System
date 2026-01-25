import cv2
import numpy as np
import time
from collections import deque
from PyQt6.QtCore import QThread, pyqtSignal
from algorithms.vignetting import VignettingCorrector
from algorithms.event_sim import PseudoEventGen
from algorithms.alignment import ImageAligner
from config import THERMAL_W, THERMAL_H, VIS_W, VIS_H


class SyncEngine(QThread):
    # 信号: (Fusion, RawThermalDisp, RawEventDisp, RawThermalData, Info)
    update_signal = pyqtSignal(np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict)
    log_signal = pyqtSignal(str)

    def __init__(self, q_vis, q_therm):
        super().__init__()
        self.q_vis, self.q_therm = q_vis, q_therm
        self.running = True
        self.mode = "LOCKED"
        self.checker_mode = False

        self.algo_vign = VignettingCorrector()
        self.algo_align = ImageAligner()
        self.algo_evt = PseudoEventGen(width=VIS_W, height=VIS_H, threshold=20)

        self.cache_t_raw = np.zeros((THERMAL_H, THERMAL_W), dtype=np.uint16)
        self.fps_cnt = 0;
        self.curr_fps = 0.0;
        self.fps_timer = time.time()
        self.last_ui = 0;
        self.ui_interval = 0.016

    def set_mode(self, mode):
        self.mode = mode
        self.log_signal.emit(f">>> MODE: {mode}")

    def update_align_params(self, dx=0, dy=0, d_scale=None, set_scale=None, set_angle=None, toggle_checker=False):
        nx = self.algo_align.x + dx
        ny = self.algo_align.y + dy
        ns = self.algo_align.scale
        if d_scale: ns *= d_scale
        if set_scale: ns = set_scale
        na = self.algo_align.angle
        if set_angle is not None: na = set_angle

        if toggle_checker:
            self.checker_mode = not self.checker_mode
            self.log_signal.emit(f"> CHECKER PATTERN: {'ON' if self.checker_mode else 'OFF'}")

        self.algo_align.update_params(x=nx, y=ny, scale=ns, angle=na, opacity=0.5)

    def rotate_image(self, image, angle):
        h, w = image.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        return cv2.warpAffine(image, M, (w, h))

    def stop(self):
        self.running = False; self.wait()

    def run(self):
        self.log_signal.emit("[CORE] TACTICAL FUSION ONLINE")

        while self.running:
            if len(self.q_vis) == 0: self.msleep(1); continue
            while len(self.q_vis) > 1: self.q_vis.popleft()

            v_ts, _, v_raw = self.q_vis.popleft()
            if self.q_therm: self.cache_t_raw = self.q_therm.pop()[2]

            v_corr = self.algo_vign.process(v_raw)
            e_full_mask = self.algo_evt.process(v_corr)
            if len(v_corr.shape) == 2:
                v_bg = cv2.cvtColor(v_corr, cv2.COLOR_GRAY2BGR)
            else:
                v_bg = v_corr

            # === 热成像智能宽容度算法 (Smart Span Control) ===
            raw_f = self.cache_t_raw.astype(np.float32)
            temp_c = raw_f / 64.0 - 273.15

            # 统计值
            t_min = np.percentile(temp_c, 1)
            t_max = np.percentile(temp_c, 99)
            t_median = np.median(temp_c)

            current_span = t_max - t_min

            # === 核心修改：冷色锚定策略 ===
            MIN_SPAN = 10.0  # 强制最小温宽 10度

            if current_span < MIN_SPAN:
                # 环境平坦（只有18度）：
                # 不再居中，而是把当前温度按在底部 (蓝色区)
                # 比如当前18度，我们将 min 设为 16度，max 设为 26度
                # 这样 18度 只占 20% 的位置 -> 深蓝色
                display_min = t_median - 2.0
                display_max = display_min + MIN_SPAN
            else:
                # 高动态范围（有手）：
                # 正常拉伸，显示全红全蓝
                display_min = t_min
                display_max = t_max

            # 归一化映射
            t_norm_f = (temp_c - display_min) / (display_max - display_min) * 255.0
            t_norm = np.clip(t_norm_f, 0, 255).astype(np.uint8)
            t_color_full = cv2.applyColorMap(t_norm, cv2.COLORMAP_JET)

            # === 后续处理保持不变 ===
            e_full_disp = np.zeros_like(v_bg)
            e_full_disp[e_full_mask > 0] = [0, 255, 0]

            tx, ty, tw, th, angle, opacity = self.algo_align.get_transform_params()
            t_scaled = cv2.resize(t_color_full, (tw, th))
            t_rotated = self.rotate_image(t_scaled, angle)

            x1 = max(0, tx);
            y1 = max(0, ty)
            x2 = min(VIS_W, tx + tw);
            y2 = min(VIS_H, ty + th)
            vw = x2 - x1;
            vh = y2 - y1

            final_fusion = None

            if vw > 0 and vh > 0:
                v_crop = v_bg[y1:y2, x1:x2]
                ox = x1 - tx;
                oy = y1 - ty
                t_crop = t_rotated[oy:oy + vh, ox:ox + vw]

                if self.mode == "ADJUST":
                    fusion_display = v_bg.copy()
                    if t_crop.shape == v_crop.shape:
                        if self.checker_mode:
                            block_size = 32
                            grid_y, grid_x = np.indices((vh, vw))
                            checker_mask = ((grid_x // block_size) + (grid_y // block_size)) % 2 == 0
                            checker_mask_3d = np.dstack([checker_mask] * 3)
                            blend = np.where(checker_mask_3d, v_crop, t_crop)
                            fusion_display[y1:y2, x1:x2] = blend
                        else:
                            blend = cv2.addWeighted(v_crop, 1.0, t_crop, 0.5, 0)
                            fusion_display[y1:y2, x1:x2] = blend

                    cv2.rectangle(fusion_display, (x1, y1), (x2, y2), (0, 255, 255), 2)
                    final_fusion = fusion_display
                else:
                    roi_fusion = v_crop.copy()
                    if t_crop.shape == roi_fusion.shape:
                        roi_fusion = cv2.addWeighted(roi_fusion, 0.5, t_crop, 0.8, 0)
                    e_crop = e_full_mask[y1:y2, x1:x2]
                    roi_fusion[e_crop > 0] = [0, 255, 0]
                    final_fusion = roi_fusion
            else:
                final_fusion = v_bg if self.mode == "ADJUST" else np.zeros((480, 640, 3), dtype=np.uint8)

            self.fps_cnt += 1
            if time.time() - self.fps_timer >= 1.0:
                self.curr_fps = self.fps_cnt;
                self.fps_cnt = 0;
                self.fps_timer = time.time()
            now = time.time()
            if now - self.last_ui > self.ui_interval:
                info = {"fps": self.curr_fps, "mode": self.mode}
                self.update_signal.emit(final_fusion, t_color_full, e_full_disp, self.cache_t_raw, info)
                self.last_ui = now