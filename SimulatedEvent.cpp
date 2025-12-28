#include "SimulatedEvent.h"

SimulatedEvent::SimulatedEvent(double threshold) : threshold(threshold) {}

cv::Mat SimulatedEvent::processFrame(const cv::Mat& gray_frame) {
    cv::Mat gray;
    if (gray_frame.channels() > 1) cv::cvtColor(gray_frame, gray, cv::COLOR_BGR2GRAY);
    else gray = gray_frame;

    cv::Mat current_f, current_log;
    gray.convertTo(current_f, CV_32F, 1.0 / 255.0);
    cv::log(current_f + 0.01f, current_log);

    if (last_log_frame.empty() || last_log_frame.size() != gray.size()) {
        current_log.copyTo(last_log_frame);
        return cv::Mat::zeros(gray.size(), CV_8U) + 127;
    }

    cv::Mat diff = current_log - last_log_frame;
    current_log.copyTo(last_log_frame);

    cv::Mat event_map(gray.size(), CV_8U, cv::Scalar(127));
    event_map.setTo(255, diff > threshold);
    event_map.setTo(0, diff < -threshold);

    return event_map;
}