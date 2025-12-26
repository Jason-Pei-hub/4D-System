#ifndef _SAMPLE_H_
#define _SAMPLE_H_

#if defined(_WIN32)
#include <Windows.h>
#elif defined(linux) || defined(unix)
#include <unistd.h>
#include <sys/time.h>    
#include <sys/resource.h>
#endif

#include <stdio.h>

/* 引入热成像核心头文件 */
#include "cmd.h"
#include "camera.h"
#include "display.h"
#include "temperature.h"

/* 版本号定义 */
#define IR_SAMPLE_VERSION "libirsample tiny1c 1.7.3"

/* 日志级别枚举定义 */
typedef enum {
	DEBUG_PRINT = 0,
	ERROR_PRINT,
	NO_PRINT,
}log_level_t;

/* 功能开关宏定义（默认关闭） */
//#define USER_FUNCTION_CALLBACK
//#define LOOP_TEST
//#define UPDATE_FW

#ifdef __cplusplus
extern "C" {
#endif

	/**
	 * @brief 【新增】热成像演示入口函数
	 * 将原 sample.cpp 中的 main 函数改名而来。
	 * 调用此函数将启动热成像的初始化、图像流、温度计算和显示线程。
	 * @return int 执行状态
	 */
	int run_thermal_demo(void);

	/**
	 * @brief 初始化流媒体帧信息
	 * @param stream_frame_info 指向流信息的指针
	 */
	void load_stream_frame_info(StreamFrameInfo_t* stream_frame_info);

	/**
	 * @brief 打印版本号并设置日志级别
	 */
	void print_version_and_setup_log();

#ifdef __cplusplus
}
#endif

#endif /* _SAMPLE_H_ */