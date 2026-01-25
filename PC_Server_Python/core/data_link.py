# core/data_link.py
import socket
import struct
import numpy as np
import cv2
from PyQt6.QtCore import QThread, pyqtSignal
from config import HOST, THERMAL_W, THERMAL_H


class DataReceiver(QThread):
    log_signal = pyqtSignal(str)

    def __init__(self, port, queue, mode):
        super().__init__()
        self.port = port
        self.queue = queue
        self.mode = mode
        self.running = True

    def recv_all(self, sock, count):
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
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((HOST, self.port))
            s.listen(1)
            self.log_signal.emit(f"[{self.mode}] LISTENING: {self.port}")
        except Exception as e:
            self.log_signal.emit(f"ERR: {e}")
            return

        while self.running:
            try:
                conn, addr = s.accept()
                self.log_signal.emit(f"[{self.mode}] CONNECTED: {addr[0]}")
                while self.running:
                    head = self.recv_all(conn, 16)
                    if not head: break
                    ts, size, fid = struct.unpack("=QII", head)
                    payload = self.recv_all(conn, size)
                    if not payload: break

                    data = None
                    if self.mode == "video":
                        data = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
                    elif self.mode == "thermal":
                        if size == THERMAL_W * THERMAL_H * 2:
                            data = np.frombuffer(payload, dtype=np.uint16).reshape((THERMAL_H, THERMAL_W))

                    if data is not None:
                        if len(self.queue) >= 50: self.queue.popleft()
                        self.queue.append((ts, fid, data))
            except:
                pass
            finally:
                if 'conn' in locals(): conn.close()

    def stop(self):
        self.running = False
        self.wait()