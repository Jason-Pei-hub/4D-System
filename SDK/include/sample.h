#ifndef SAMPLE_H
#define SAMPLE_H

#include "data.h"
#include "camera.h"
#include "temperature.h"

#ifdef __cplusplus
extern "C" {
#endif
    void load_stream_frame_info(StreamFrameInfo_t* stream_frame_info);
    void print_version_and_setup_log();
#ifdef __cplusplus
}
#endif

// 导出 SDK 的线程函数，匹配 camera.cpp 和 temperature.cpp 的定义
void* stream_function(void* arg);
void* temperature_function(void* arg);

#endif