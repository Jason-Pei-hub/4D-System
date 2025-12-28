#include "OV9281_Driver.h"
#include <iostream>
#include <thread>
#include <chrono>
#include <string>
#include <cstdlib>
#include <signal.h> // 用于捕捉退出信号

OV9281_Driver::OV9281_Driver() : is_running(false), actual_fps(0) {}
OV9281_Driver::~OV9281_Driver() { stop(); }

bool OV9281_Driver::init(int camera_id, int target_fps) {
    if (cap.isOpened()) cap.release();
    
    std::cout << ">>> [Driver] 正在初始化 (回归稳定版: 软解+多线程)..." << std::endl;

    // 1. 外部曝光控制 (保持 2ms 曝光 + 满增益)
    std::string dev = "/dev/video" + std::to_string(camera_id);
    std::string setup_cmd = 
        "v4l2-ctl -d " + dev + " -c auto_exposure=1 -c exposure_time_absolute=20 -c gain=255";
    int ret = system(setup_cmd.c_str());
    if (ret != 0) std::cerr << ">>> [Warn] v4l2-ctl 设置可能失败，请检查 USB 连接" << std::endl;

    // 2. 管道构建 (回到 jpegdec，因为 v4l2jpegdec 导致了死锁)
    // 加入 drop=true 确保处理不过来时丢帧，而不是卡死
    std::string pipeline = 
        "v4l2src device=" + dev + " io-mode=2 ! "
        "image/jpeg, width=1280, height=800, framerate=120/1 ! "
        "queue max-size-buffers=3 leaky=downstream ! " // 稍微加大缓冲
        "jpegdec ! "                                   // 软件解码 (经测试可达 95fps)
        "queue max-size-buffers=3 ! "
        "videoconvert ! "
        "appsink sync=false drop=true max-buffers=1";

    std::cout << ">>> [Pipeline] " << pipeline << std::endl;

    // 3. 打开
    try {
        cap.open(pipeline, cv::CAP_GSTREAMER);
    } catch (...) {
        std::cerr << ">>> [Fatal] GStreamer 打开异常！" << std::endl;
        return false;
    }
    
    if (!cap.isOpened()) {
        std::cerr << ">>> [Error] 无法启动摄像头，可能是设备号变了或 USB 掉线。" << std::endl;
        return false;
    }

    std::cout << ">>> [Success] 管道启动成功！" << std::endl;
    return true;
}

void OV9281_Driver::start() {
    is_running = true;
    worker = std::thread(&OV9281_Driver::capture_loop, this);
}

void OV9281_Driver::stop() {
    is_running = false;
    // 强制释放，防止卡死
    if (cap.isOpened()) cap.release();
    if (worker.joinable()) worker.join();
}

void OV9281_Driver::capture_loop() {
    cv::Mat tmp;
    int frame_count = 0;
    double t_start = (double)cv::getTickCount();
    int error_count = 0; // 错误计数器

    std::cout << ">>> 9281 采集循环开始 <<<" << std::endl;

    while (is_running) {
        bool read_success = false;
        
        // 尝试读取，如果卡住或报错
        try {
            read_success = cap.read(tmp);
        } catch (...) {
            std::cerr << ">>> [Exception] 读取发生异常！" << std::endl;
            read_success = false;
        }

        if (read_success && !tmp.empty()) {
            error_count = 0; // 重置错误计数
            {
                std::lock_guard<std::mutex> lock(mtx);
                tmp.copyTo(latest_frame);
            }
            frame_count++;
            if (frame_count >= 60) {
                double now = (double)cv::getTickCount();
                double fps = 60.0 / ((now - t_start) / cv::getTickFrequency());
                printf("\r[OV9281 Stable] FPS: %.2f   ", fps);
                fflush(stdout);
                t_start = now; frame_count = 0;
            }
        } else {
            // 连续读取失败处理
            error_count++;
            if (error_count > 100) {
                std::cerr << "\n>>> [Fatal] 连续 100 帧读取失败，疑似 USB 掉线！停止采集。" << std::endl;
                is_running = false;
                break;
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(5));
        }
    }
    std::cout << "\n>>> 采集线程安全退出 <<<" << std::endl;
}

bool OV9281_Driver::getFrame(cv::Mat& frame) {
    std::lock_guard<std::mutex> lock(mtx);
    if (latest_frame.empty()) return false;
    latest_frame.copyTo(frame);
    return true;
}