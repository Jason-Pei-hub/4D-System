#include "sample.h"
#include <stdio.h>

// 引用 camera.cpp 中定义的全局变量
extern int stream_time; 

void load_stream_frame_info(StreamFrameInfo_t* stream_frame_info)
{
    // 【核心修复 1】解决热成像运行一会就卡死的问题
    // 原代码里 stream_time 默认是 100秒，这里强制改为无限大
    stream_time = 999999; 

    // 1. 设置硬件参数
    stream_frame_info->image_info.width = stream_frame_info->camera_param.width;
    stream_frame_info->image_info.height = stream_frame_info->camera_param.height / 2;

    // 2. 【核心修复 2】强制使用 YUV422
    stream_frame_info->image_info.pseudo_color_status = PSEUDO_COLOR_ON; 
    stream_frame_info->image_info.input_format = INPUT_FMT_YUV422; 
    stream_frame_info->image_info.output_format = OUTPUT_FMT_YUV422; 

    // 3. 【核心修复 3】内存大小 *2
    stream_frame_info->image_byte_size = stream_frame_info->image_info.width * stream_frame_info->image_info.height * 2;
    stream_frame_info->temp_byte_size = stream_frame_info->temp_info.width * stream_frame_info->temp_info.height * 2;

    create_data_demo(stream_frame_info);
}