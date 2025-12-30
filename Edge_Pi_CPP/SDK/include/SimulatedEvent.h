#ifndef SIMULATED_EVENT_H
#define SIMULATED_EVENT_H
#include <opencv2/opencv.hpp>

class SimulatedEvent {
public:
    SimulatedEvent(double threshold = 0.40);
    cv::Mat processFrame(const cv::Mat& gray_frame);
private:
    cv::Mat last_log_frame;
    double threshold;
};
#endif