#include "OV9281_Driver.h"
#include "sample.h"
#include <opencv2/opencv.hpp>
#include <pthread.h>
#include <semaphore.h>
#include <iostream>
#include <string>
#include <cstdlib>

extern sem_t image_sem, temp_sem, image_done_sem, temp_done_sem;

int main() {
    system("xhost +local:");
    system("sudo chmod -R 777 /dev/bus/usb/");

    // 1. 初始化热成像
    StreamFrameInfo_t thermal_info = { 0 };
    init_pthread_sem();
    if (ir_camera_open(&thermal_info.camera_param) >= 0) {
        load_stream_frame_info(&thermal_info);
        ir_camera_stream_on(&thermal_info);
        pthread_t t1, t2;
        pthread_create(&t1, NULL, stream_function, &thermal_info);
        pthread_create(&t2, NULL, temperature_function, &thermal_info);
    }

    // 2. 初始化 OV9281 (GStreamer 模式)
    OV9281_Driver ov_cam;
    // 尝试 video0
    if (!ov_cam.init(0, 120)) { 
        // 尝试 video2
        if (!ov_cam.init(2, 120)) return -1;
    }
    ov_cam.start();

    // 3. 窗口显示
    cv::namedWindow("OV9281", cv::WINDOW_NORMAL);
    cv::resizeWindow("OV9281", 640, 400);

    cv::Mat ov_raw;
    cv::Mat ir_raw_yuv, ir_display_bgr;

    while (true) {
        // --- 9281 ---
        if (ov_cam.getFrame(ov_raw)) {
            static int skip = 0;
            if (++skip % 2 == 0) {
                cv::imshow("OV9281", ov_raw);
                skip = 0;
            }
        }

        // --- 热成像 ---
        if (sem_trywait(&image_sem) == 0) {
            if (thermal_info.image_frame != NULL) {
                ir_raw_yuv = cv::Mat(thermal_info.image_info.height, thermal_info.image_info.width, CV_8UC2, thermal_info.image_frame);
                cv::cvtColor(ir_raw_yuv, ir_display_bgr, cv::COLOR_YUV2BGR_YUYV);
                if (!ir_display_bgr.empty()) cv::imshow("Thermal", ir_display_bgr);
            }
            sem_post(&image_done_sem); 
        }
        if (sem_trywait(&temp_sem) == 0) sem_post(&temp_done_sem); 

        if (cv::waitKey(1) == 27) break; 
    }
    
    ov_cam.stop();
    destroy_pthread_sem();
    return 0;
}