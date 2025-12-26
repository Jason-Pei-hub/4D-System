#include "OV9281_Driver.h"
#include <iostream>

OV9281_Driver::OV9281_Driver() : is_running(false), actual_fps(0) {}
OV9281_Driver::~OV9281_Driver() { stop(); }

bool OV9281_Driver::init(int camera_id, int target_fps) {
    // 硬件规格匹配
    if (target_fps >= 420) {
        actual_width = 320; actual_height = 240; actual_fps = 420;
    }
    else if (target_fps >= 210) {
        actual_width = 640; actual_height = 400; actual_fps = 210;
    }
    else {
        actual_width = 1280; actual_height = 800; actual_fps = 120;
    }

    if (cap.isOpened()) cap.release();

#if defined(_WIN32)
    cap.open(camera_id, cv::CAP_DSHOW); // Windows 环境
#else
    cap.open(camera_id, cv::CAP_V4L2);  // Linux 环境
#endif

    if (!cap.isOpened()) return false;

    // 核心参数锁定
    cap.set(cv::CAP_PROP_FOURCC, cv::VideoWriter::fourcc('M', 'J', 'P', 'G'));
    cap.set(cv::CAP_PROP_FRAME_WIDTH, actual_width);
    cap.set(cv::CAP_PROP_FRAME_HEIGHT, actual_height);
    cap.set(cv::CAP_PROP_FPS, actual_fps);
    cap.set(cv::CAP_PROP_AUTO_EXPOSURE, 1);
    cap.set(cv::CAP_PROP_EXPOSURE, -8);

    return true;
}

void OV9281_Driver::start() {
    is_running = true;
    worker = std::thread(&OV9281_Driver::capture_loop, this);
}

void OV9281_Driver::stop() {
    is_running = false;
    if (worker.joinable()) worker.join();
    if (cap.isOpened()) cap.release();
}

void OV9281_Driver::capture_loop() {
    cv::Mat tmp;
    while (is_running) {
        if (cap.read(tmp)) {
            std::lock_guard<std::mutex> lock(mtx);
            tmp.copyTo(latest_frame);
        }
    }
}

bool OV9281_Driver::getFrame(cv::Mat& frame) {
    std::lock_guard<std::mutex> lock(mtx);
    if (latest_frame.empty()) return false;
    latest_frame.copyTo(frame);
    return true;
}