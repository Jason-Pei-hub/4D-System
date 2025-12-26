#ifndef OV9281_DRIVER_H
#define OV9281_DRIVER_H

#include <opencv2/opencv.hpp>
#include <thread>
#include <atomic>
#include <mutex>

class OV9281_Driver {
public:
    OV9281_Driver();
    ~OV9281_Driver();

    bool init(int camera_id, int target_fps);
    void start();
    void stop();
    bool getFrame(cv::Mat& frame);
    int getActualFPS() const { return actual_fps; }

private:
    void capture_loop();
    cv::VideoCapture cap;
    std::thread worker;
    std::atomic<bool> is_running;
    std::mutex mtx;
    cv::Mat latest_frame;
    int actual_width, actual_height, actual_fps;
};

#endif