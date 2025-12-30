#include "OV9281_Driver.h"
#include "sample.h"
#include <opencv2/opencv.hpp>
#include <pthread.h>
#include <semaphore.h>
#include <iostream>
#include <vector>
#include <sys/socket.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <cstring>
#include <csignal>
#include <sys/time.h>

// --- 宏定义 ---
#define TINY_WIDTH 256
#define TINY_HEIGHT 192

// --- 配置区域 ---
#define PC_IP "192.168.1.100"  // 电脑端 IP
#define PORT_VIDEO 8888
#define PORT_THERMAL 8889

extern sem_t image_sem, temp_sem, image_done_sem, temp_done_sem;

struct PacketHeader {
    uint64_t timestamp_us;
    uint32_t data_size;
    uint32_t frame_id;
};

// --- 网络辅助函数 ---
bool send_all(int sock, const void* data, size_t size) {
    const char* ptr = (const char*)data;
    size_t total_sent = 0;
    while (total_sent < size) {
        ssize_t sent = send(sock, ptr + total_sent, size - total_sent, MSG_NOSIGNAL);
        if (sent <= 0) return false;
        total_sent += sent;
    }
    return true;
}

int try_connect(int port) {
    int sock = socket(AF_INET, SOCK_STREAM, 0);
    if (sock < 0) return -1;

    struct timeval tv;
    tv.tv_sec = 2;
    tv.tv_usec = 0;
    setsockopt(sock, SOL_SOCKET, SO_SNDTIMEO, (const char*)&tv, sizeof tv);

    struct sockaddr_in serv_addr;
    serv_addr.sin_family = AF_INET;
    serv_addr.sin_port = htons(port);
    if (inet_pton(AF_INET, PC_IP, &serv_addr.sin_addr) <= 0) {
        close(sock);
        return -1;
    }

    if (connect(sock, (struct sockaddr *)&serv_addr, sizeof(serv_addr)) < 0) {
        close(sock);
        return -1;
    }
    std::cout << "[Network] Connected to PC on port " << port << std::endl;
    return sock;
}

// --- 线程 1: OV9281 高速视频发送 ---
void* video_sender_thread(void* arg) {
    OV9281_Driver* driver = (OV9281_Driver*)arg;
    RawDataPacket packet;
    PacketHeader header;
    int sock = -1;

    while (true) {
        if (sock < 0) {
            sock = try_connect(PORT_VIDEO);
            if (sock < 0) {
                sleep(1);
                continue;
            }
        }

        if (driver->getLatestRawFrame(packet)) {
            header.timestamp_us = packet.timestamp_us;
            header.data_size = packet.data.size();
            header.frame_id = packet.frame_id;

            bool ok = send_all(sock, &header, sizeof(header));
            if (ok) ok = send_all(sock, packet.data.data(), packet.data.size());

            if (!ok) {
                std::cerr << "[Video] Disconnected. Retrying..." << std::endl;
                close(sock);
                sock = -1;
            }
        } else {
            std::this_thread::sleep_for(std::chrono::microseconds(500));
        }
    }
    return NULL;
}

// --- 线程 2: 热成像发送 (高性能优化版) ---
void* thermal_sender_thread(void* arg) {
    StreamFrameInfo_t* info = (StreamFrameInfo_t*)arg;
    PacketHeader header;
    uint32_t frame_id = 0;
    int sock = -1;

    // 【优化1】本地双缓冲，用于快速拷贝
    size_t data_len = TINY_WIDTH * TINY_HEIGHT * 2;
    std::vector<uint8_t> local_buffer(data_len);

    std::cout << ">>> [Thermal Thread] High Performance Mode (Buffer Copy)" << std::endl;

    while (true) {
        // 1. 等待 SDK 数据
        sem_wait(&temp_sem);

        // 2. 获取时间戳
        struct timeval tv;
        gettimeofday(&tv, NULL);
        uint64_t now_us = (uint64_t)tv.tv_sec * 1000000 + tv.tv_usec;

        // 3. 【优化2】极速拷贝数据，然后立即释放信号量
        // 这样 SDK 就可以立刻去采集下一帧，不需要等待网络发送完成
        bool has_data = (info->temp_frame != NULL);
        if (has_data) {
            memcpy(local_buffer.data(), info->temp_frame, data_len);
        }
        
        // 4. 立即通知 SDK 继续干活！
        sem_post(&temp_done_sem);

        // 5. 接下来慢慢处理网络发送（不阻塞采集）
        if (!has_data) continue;

        if (sock < 0) {
            sock = try_connect(PORT_THERMAL);
        }

        if (sock >= 0) {
            header.timestamp_us = now_us;
            header.data_size = data_len;
            header.frame_id = frame_id++;

            bool ok = send_all(sock, &header, sizeof(header));
            if (ok) ok = send_all(sock, local_buffer.data(), data_len);

            if (ok && frame_id % 30 == 0) { // 每30帧打印一次，约1秒一次
                std::cout << "[Thermal] FPS Stable. Sent frame " << frame_id << std::endl;
            }

            if (!ok) {
                std::cerr << "[Thermal] Send failed!" << std::endl;
                close(sock);
                sock = -1;
            }
        }
    }
    return NULL;
}

// --- 主程序 ---
int main() {
    signal(SIGPIPE, SIG_IGN);
    system("sudo chmod -R 777 /dev/bus/usb/");

    std::cout << ">>> 4D System Starting..." << std::endl;

    // 1. 初始化热成像
    StreamFrameInfo_t thermal_info = { 0 };
    init_pthread_sem(); 
    
    if (ir_camera_open(&thermal_info.camera_param) >= 0) {
        load_stream_frame_info(&thermal_info);
        ir_camera_stream_on(&thermal_info);
        
        pthread_t t1;
        pthread_create(&t1, NULL, stream_function, &thermal_info);
        std::cout << "[Init] Thermal Camera OK." << std::endl;
    } else {
        std::cerr << "[Error] Thermal Camera Init Failed!" << std::endl;
    }

    // 2. 初始化 OV9281
    OV9281_Driver ov_cam;
    int retry = 0;
    while (!ov_cam.init(0, 120) && !ov_cam.init(2, 120)) {
        std::cerr << "[Warn] OV9281 not found, retrying..." << std::endl;
        sleep(1);
        if (++retry > 10) break;
    }
    ov_cam.start();

    // 3. 启动网络线程
    pthread_t st1, st2;
    pthread_create(&st1, NULL, video_sender_thread, &ov_cam);
    pthread_create(&st2, NULL, thermal_sender_thread, &thermal_info);

    // 4. 主线程保活与信号清理 (核心优化区域)
    std::cout << ">>> Main loop running: Fast consuming image_sem..." << std::endl;
    while (true) {
        // 【优化3】不再 sleep(1)！
        // 使用阻塞等待 sem_wait，只要有信号就立即处理。
        // 这确保了 SDK 的 image_sem 被秒级释放，不会卡住采集循环。
        sem_wait(&image_sem);
        
        // 我们不需要热成像的视频流(YUV)，直接扔掉
        sem_post(&image_done_sem);
        
        // 这一步非常快，几乎不消耗 CPU
    }

    ov_cam.stop();
    destroy_pthread_sem();
    return 0;
}