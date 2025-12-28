#ifndef OV9281_DRIVER_H
#define OV9281_DRIVER_H

#include <opencv2/opencv.hpp>
#include <thread>
#include <mutex>

class OV9281_Driver {
public:
    OV9281_Driver();
    ~OV9281_Driver();

    bool init(int camera_id, int target_fps);
    void start();
    void stop();
    bool getFrame(cv::Mat& frame);
    
    // 【新增】运行时调参接口
    void setHighSpeedExposure(); 

private:
    void capture_loop();

    cv::VideoCapture cap;
    bool is_running;
    std::thread worker;
    std::mutex mtx;
    cv::Mat latest_frame;
    
    int actual_width;
    int actual_height;
    int actual_fps;
};

#endif