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
    # (Fusion, Therm, Event, ROI, Depth, Info)
    update_signal = pyqtSignal(np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict)
    log_signal = pyqtSignal(str)

    def __init__(self, q_vis, q_therm):
        super().__init__()
        self.q_vis, self.q_therm = q_vis, q_therm
        self.running = True
        self.mode = "LOCKED"
        self.checker_mode = False

        try:
            self.algo_vign = VignettingCorrector()
            self.algo_align = ImageAligner()
            self.algo_evt = PseudoEventGen(width=VIS_W, height=VIS_H, threshold=20)
        except:
            pass

        self.cache_t_raw = np.zeros((THERMAL_H, THERMAL_W), dtype=np.uint16)
        # 缓冲仅做计算用，不用于回溯显示
        self.event_buffer = deque(maxlen=20)
        self.fps_cnt = 0;
        self.curr_fps = 0.0;
        self.fps_timer = time.time()

    def set_mode(self, mode):
        self.mode = mode
        self.log_signal.emit(f">>> MODE: {mode}")

    def update_align_params(self, dx=0, dy=0, d_scale=None, set_scale=None, set_angle=None, toggle_checker=False):
        try:
            nx = self.algo_align.x + dx
            ny = self.algo_align.y + dy
            ns = self.algo_align.scale
            if d_scale: ns *= d_scale
            if set_scale: ns = set_scale
            na = self.algo_align.angle
            if set_angle is not None: na = set_angle
            if toggle_checker: self.checker_mode = not self.checker_mode
            self.algo_align.update_params(x=nx, y=ny, scale=ns, angle=na, opacity=0.5)
        except:
            pass

    def rotate_image(self, image, angle):
        h, w = image.shape[:2]
        M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
        return cv2.warpAffine(image, M, (w, h))

    def run(self):
        self.log_signal.emit("[CORE] ENGINE STARTED")

        # === 视觉优化：给黑窗口加上文字，方便区分 ===
        # 1. ROI 占位图 (带紫色边框和文字)
        black_roi = np.zeros((120, 120, 3), dtype=np.uint8)
        cv2.rectangle(black_roi, (0, 0), (120, 120), (255, 0, 255), 2)
        cv2.putText(black_roi, "ROI", (30, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 0, 255), 2)
        cv2.putText(black_roi, "VIEW", (30, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 255), 1)

        # 2. Depth 占位图 (带黄色边框和文字)
        black_depth = np.zeros((120, 120, 3), dtype=np.uint8)
        cv2.rectangle(black_depth, (0, 0), (120, 120), (0, 255, 255), 2)
        cv2.putText(black_depth, "DEPTH", (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        cv2.putText(black_depth, "MAP", (40, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

        while self.running:
            try:
                # 1. 获取可见光
                if len(self.q_vis) == 0:
                    self.msleep(1)
                    continue

                # 强制最新，防止跳帧
                while len(self.q_vis) > 1: self.q_vis.popleft()
                v_ts, _, v_raw = self.q_vis.popleft()

                v_corr = self.algo_vign.process(v_raw)
                e_mask = self.algo_evt.process(v_corr)

                # 存入缓冲
                self.event_buffer.append((e_mask, v_ts, v_corr))

                # 直接使用最新帧做背景，确保丝滑
                v_bg = cv2.cvtColor(v_corr, cv2.COLOR_GRAY2BGR)
                e_disp = np.zeros_like(v_bg)
                e_disp[e_mask > 0] = [0, 255, 0]

                # 2. 获取热成像
                if len(self.q_therm) > 0:
                    while len(self.q_therm) > 1: self.q_therm.pop()
                    t_ts, _, t_raw = self.q_therm.pop()
                    self.cache_t_raw = t_raw

                raw_f = self.cache_t_raw.astype(np.float32)
                temp_c = raw_f / 64.0 - 273.15
                t_min, t_max = np.min(temp_c), np.max(temp_c)
                if t_max - t_min < 2.0: t_max = t_min + 5.0
                t_norm = ((temp_c - t_min) / (t_max - t_min) * 255).astype(np.uint8)
                t_color = cv2.applyColorMap(t_norm, cv2.COLORMAP_JET)

                # 3. 融合
                tx, ty, tw, th, angle, _ = self.algo_align.get_transform_params()
                t_scaled = cv2.resize(t_color, (tw, th))
                t_rotated = self.rotate_image(t_scaled, angle)

                x1 = max(0, tx);
                y1 = max(0, ty)
                x2 = min(VIS_W, tx + tw);
                y2 = min(VIS_H, ty + th)
                vw = x2 - x1;
                vh = y2 - y1

                final_fusion = v_bg.copy()

                if vw > 0 and vh > 0:
                    v_crop = v_bg[y1:y2, x1:x2]
                    ox = x1 - tx;
                    oy = y1 - ty

                    if oy + vh <= t_rotated.shape[0] and ox + vw <= t_rotated.shape[1]:
                        t_crop = t_rotated[oy:oy + vh, ox:ox + vw]

                        if self.checker_mode:
                            mask = ((np.indices((vh, vw))[0] // 32 + np.indices((vh, vw))[1] // 32) % 2 == 0)
                            mask = np.dstack([mask] * 3)
                            blend = np.where(mask, v_crop, t_crop)
                            final_fusion[y1:y2, x1:x2] = blend
                        else:
                            blend = cv2.addWeighted(v_crop, 0.6, t_crop, 0.7, 0)
                            final_fusion[y1:y2, x1:x2] = blend

                        # 只有在 ADJUST 模式才画框
                        if self.mode != "LOCKED":
                            cv2.rectangle(final_fusion, (x1, y1), (x2, y2), (0, 255, 0), 2)
                        else:
                            # LOCKED 模式自动裁切特写
                            final_fusion = blend

                # 4. 发送
                self.fps_cnt += 1
                if time.time() - self.fps_timer >= 1.0:
                    self.curr_fps = self.fps_cnt;
                    self.fps_cnt = 0;
                    self.fps_timer = time.time()

                info = {"fps": self.curr_fps, "mode": self.mode}
                # 发送带文字的 black_roi 和 black_depth
                self.update_signal.emit(final_fusion, t_color, e_disp, black_roi, black_depth, info)

            except Exception as e:
                print(f"Sync: {e}");
                self.msleep(10)

    def stop(self):
        self.running = False;
        self.wait()