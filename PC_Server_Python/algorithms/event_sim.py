import cv2
import numpy as np


class PseudoEventGen:
    def __init__(self, width=1280, height=800, threshold=25):
        self.w = width
        self.h = height
        # 阈值调高：防止噪点导致全屏白
        self.threshold = threshold
        self.prev_frame = None

    def process(self, curr_img_raw):
        """
        [极速版] 瞬态差分事件生成
        Ref: "Event-based Sensor Model", simulating Log-Intensity changes.
        """
        if curr_img_raw is None: return None

        # 1. 极速预处理
        # 9281 的原始数据 (uint8)
        # 真实事件相机对"对数光强"敏感，这能抵抗光照不均
        # Log 运算比较慢，我们用近似算法：直接用 int16 做差分，避免溢出
        curr = curr_img_raw.astype(np.int16)

        if self.prev_frame is None:
            self.prev_frame = curr
            return np.zeros((self.h, self.w), dtype=np.uint8)

        # 2. 计算差分 (Delta)
        # diff = Current - Previous
        diff = cv2.subtract(curr, self.prev_frame)

        # 3. 极性阈值清洗 (Thresholding)
        # 只有变化幅度超过阈值的像素才被认为是"事件"
        # 正向变化 (变亮) -> 255
        # 负向变化 (变暗) -> 255 (或者区分颜色，这里为了融合统一用255)

        # 这是一个极速操作：
        # abs(diff) > threshold
        abs_diff = np.abs(diff)

        # 自适应阈值：如果画面太亮/太白，自动提高门槛
        # 简单统计一下平均变化量，如果全屏都在变（白屏），就动态提高阈值
        mean_change = np.mean(abs_diff)
        dynamic_thresh = self.threshold + int(mean_change * 1.5)

        # 生成掩码 (0 或 255)
        _, event_mask = cv2.threshold(abs_diff.astype(np.uint8), dynamic_thresh, 255, cv2.THRESH_BINARY)

        # 4. 形态学去噪 (可选，非常快)
        # 去掉孤立的噪点，只保留连续的边缘
        # kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        # event_mask = cv2.morphologyEx(event_mask, cv2.MORPH_OPEN, kernel)

        # 5. 更新上一帧
        # 关键：不要用 curr，而是用 curr 更新 prev
        self.prev_frame = curr

        return event_mask