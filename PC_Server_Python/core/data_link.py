import socket
import struct
import numpy as np
import cv2
import time
from PyQt6.QtCore import QThread, pyqtSignal
from config import VIS_W, VIS_H, THERMAL_W, THERMAL_H


class DataReceiver(QThread):
    log_signal = pyqtSignal(str)

    def __init__(self, port, queue, mode):
        super().__init__()
        self.port = port
        self.queue = queue
        self.mode = mode  # "video" or "thermal"
        self.running = True
        self.server_socket = None

    def recv_all(self, sock, count):
        """ 严格按照您提供的代码逻辑 """
        buf = b''
        while count:
            try:
                newbuf = sock.recv(count)
                if not newbuf: return None
                buf += newbuf
                count -= len(newbuf)
            except:
                return None
        return buf

    def run(self):
        # === 外层死循环：掉线后自动重启服务 ===
        while self.running:
            try:
                # 1. 创建 Socket
                self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

                # 2. 绑定 (强制 0.0.0.0 以支持热插拔和无网启动)
                # 使用 0.0.0.0，这样无论网线插没插，系统都能成功绑定到回环或网卡
                self.server_socket.bind(('0.0.0.0', self.port))
                self.server_socket.listen(1)

                self.log_signal.emit(f"[{self.mode}] WAIT: {self.port}")

                # 设置超时，防止关闭软件时卡死在 accept
                self.server_socket.settimeout(1.0)

                # 3. 等待连接循环
                while self.running:
                    try:
                        conn, addr = self.server_socket.accept()
                    except socket.timeout:
                        continue  # 超时继续等
                    except OSError:
                        break  # Socket 被关闭，重启服务

                    # 连接成功！
                    self.log_signal.emit(f"[{self.mode}] LINK: {addr[0]}")
                    conn.settimeout(None)  # 恢复阻塞模式，全速传输

                    # 4. 数据接收循环 (内层)
                    while self.running:
                        try:
                            # 收包头
                            head = self.recv_all(conn, 16)
                            if not head: break

                            ts, size, fid = struct.unpack("=QII", head)

                            # 收数据
                            payload = self.recv_all(conn, size)
                            if not payload: break

                            data = None
                            if self.mode == "video":
                                data = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
                                # 尺寸校验
                                if data is not None and (data.shape[1] != VIS_W or data.shape[0] != VIS_H):
                                    data = cv2.resize(data, (VIS_W, VIS_H))

                            elif self.mode == "thermal":
                                if size == THERMAL_W * THERMAL_H * 2:
                                    data = np.frombuffer(payload, dtype=np.uint16).reshape((THERMAL_H, THERMAL_W))

                            if data is not None:
                                # 存入队列
                                self.queue.append((ts, fid, data))

                        except Exception as e:
                            print(f"Data Error: {e}")
                            break  # 数据出错，断开重连

                    # 客户端断开，关闭连接，回到 accept 继续等
                    conn.close()
                    self.log_signal.emit(f"[{self.mode}] DISCONNECTED")

            except Exception as e:
                # 绑定失败或其他严重错误（如端口占用），等待后重试
                self.log_signal.emit(f"ERR: {e}")
                time.sleep(1)
            finally:
                # 清理资源，准备重启服务
                if self.server_socket:
                    try:
                        self.server_socket.close()
                    except:
                        pass
                self.server_socket = None

    def stop(self):
        self.running = False
        self.wait()