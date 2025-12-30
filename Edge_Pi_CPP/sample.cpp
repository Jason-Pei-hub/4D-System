#include "sample.h"
#include <stdio.h>

// 引用 camera.cpp 中定义的全局变量
extern int stream_time; 

void load_stream_frame_info(StreamFrameInfo_t* stream_frame_info)
{
    // 1. 解决运行一会卡死的问题
    stream_time = 999999; 

    // 2. 【关键修复】设置图像流参数 (256x192)
    // 摄像头返回高度384，实际包含 192图像 + 192数据，所以除以2
    stream_frame_info->image_info.width = stream_frame_info->camera_param.width;
    stream_frame_info->image_info.height = stream_frame_info->camera_param.height / 2;

    // 3. 【核心修复】设置温度流参数 (256x192)
    // 之前漏了这部分，导致温度内存没分配，数据全是乱码！
    stream_frame_info->temp_info.width = stream_frame_info->camera_param.width;
    stream_frame_info->temp_info.height = stream_frame_info->camera_param.height / 2;

    // 4. 强制使用 YUV422 (用于 Video 伪彩流)
    stream_frame_info->image_info.pseudo_color_status = PSEUDO_COLOR_ON; 
    stream_frame_info->image_info.input_format = INPUT_FMT_YUV422; 
    stream_frame_info->image_info.output_format = OUTPUT_FMT_YUV422; 

    // 5. 计算并分配内存
    // Image: YUV422 (2 bytes/pixel)
    stream_frame_info->image_byte_size = stream_frame_info->image_info.width * stream_frame_info->image_info.height * 2;
    // Temp: Raw Data (2 bytes/pixel, uint16)
    stream_frame_info->temp_byte_size = stream_frame_info->temp_info.width * stream_frame_info->temp_info.height * 2;

    create_data_demo(stream_frame_info);
    
    printf(">>> [Sample] Stream Info Loaded: Image %dx%d, Temp %dx%d\n", 
           stream_frame_info->image_info.width, stream_frame_info->image_info.height,
           stream_frame_info->temp_info.width, stream_frame_info->temp_info.height);
}