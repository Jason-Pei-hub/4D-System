#include "sample.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// 全局变量：记录帧序号
int frame_idx = 0;

// 【核心函数 1】初始化内存和参数
// 作用：告诉系统图像多大，需要分配多少内存
void load_stream_frame_info(StreamFrameInfo_t* stream_frame_info)
{
    // 1. 设置可见图像参数 (用于显示的伪彩图)
    stream_frame_info->image_info.width = stream_frame_info->camera_param.width;
    stream_frame_info->image_info.height = stream_frame_info->camera_param.height / 2; // YUV模式通常高度减半
    stream_frame_info->image_info.rotate_side = NO_ROTATE;
    stream_frame_info->image_info.mirror_flip_status = STATUS_NO_MIRROR_FLIP;
    stream_frame_info->image_info.pseudo_color_status = PSEUDO_COLOR_OFF; // 先关掉伪彩，手动处理更灵活
    stream_frame_info->image_info.img_enhance_status = IMG_ENHANCE_OFF;
    stream_frame_info->image_info.input_format = INPUT_FMT_YUV422;
    stream_frame_info->image_info.output_format = OUTPUT_FMT_BGR888; // 为了配合 OpenCV 显示，选 BGR

    // 2. 设置温度数据参数 (最需要的数据)
    stream_frame_info->temp_info.width = stream_frame_info->camera_param.width;
    stream_frame_info->temp_info.height = stream_frame_info->camera_param.height / 2;
    stream_frame_info->temp_info.rotate_side = NO_ROTATE;
    stream_frame_info->temp_info.mirror_flip_status = STATUS_NO_MIRROR_FLIP;

    // 3. 计算并设置内存大小 (宽 * 高 * 2字节)
    stream_frame_info->image_byte_size = stream_frame_info->image_info.width * stream_frame_info->image_info.height * 2;
    stream_frame_info->temp_byte_size = stream_frame_info->temp_info.width * stream_frame_info->temp_info.height * 2;

    // 4. 调用SDK内部分配内存
    create_data_demo(stream_frame_info);
}

// 【辅助函数】打印版本号并屏蔽不必要的日志
void print_version_and_setup_log()
{
    // 打印各个库的版本，确认环境没问题
    printf("Sample Version: %s\n", IR_SAMPLE_VERSION);
    printf("Lib UVC: %s\n", libiruvc_version());

    // 设置日志级别为 ERROR，防止控制台被无用的调试信息刷屏
    iruvc_log_register(IRUVC_LOG_ERROR);
    irtemp_log_register(IRTEMP_LOG_ERROR);
    irproc_log_register(IRPROC_LOG_ERROR);
    irparse_log_register(IRPARSE_LOG_ERROR);
}

// ==========================================
// 【主函数】 程序的入口
// ==========================================
int run_thermal_demo(void)
{
    // 1. 【提速】将程序优先级设为最高
    // 这样能防止 Windows 后台更新等任务抢占 CPU，减少丢帧
#if defined(_WIN32)
    SetPriorityClass(GetCurrentProcess(), HIGH_PRIORITY_CLASS);
#elif defined(linux) || defined(unix)
    setpriority(PRIO_PROCESS, 0, -20);
#endif

    // 2. 打印版本并设置日志
    print_version_and_setup_log();

    int rst;
    StreamFrameInfo_t stream_frame_info = { 0 };

    // 3. 【连接】尝试打开 USB 相机
    // 如果这里失败，通常是 USB 没插好或者驱动没装
    rst = ir_camera_open(&stream_frame_info.camera_param);
    if (rst < 0)
    {
        puts("Error: IR camera open failed!");
        getchar(); // 暂停一下看到报错
        return 0;
    }

    // 设置命令等待时间
    vdcmd_set_polling_wait_time(10000);
    command_init();

    // 4. 【分配】为图像流分配内存
    load_stream_frame_info(&stream_frame_info);

    // 5. 【启动】开启相机数据流
    rst = ir_camera_stream_on(&stream_frame_info);
    if (rst < 0)
    {
        puts("Error: Stream on failed!");
        getchar();
        return 0;
    }

    puts("Camera Init Success! Starting Threads...");

    // ==========================================
    // 6. 【核心】多线程协同工作
    // ==========================================
    pthread_t tid_stream, tid_display, tid_temperature, tid_cmd;

    // 线程1：温度计算线程 (负责算出最高温、平均温)
    pthread_create(&tid_temperature, NULL, temperature_function, &stream_frame_info);

    // 线程2：显示线程 (负责把画面画到窗口上)
    pthread_create(&tid_display, NULL, display_function, &stream_frame_info);

    // 线程3：数据流线程 (最累的搬运工，负责从USB拉取数据)
    pthread_create(&tid_stream, NULL, stream_function, &stream_frame_info);

    // 线程4：指令线程 (监听键盘按键)
    pthread_create(&tid_cmd, NULL, cmd_function, NULL);

    // ==========================================
    // 7. 【等待】主程序挂起
    // ==========================================
    // 这行代码意思是：只要 tid_stream (流线程) 不结束，主函数就不往下走。
    // 相当于一个死循环，直到你在 cmd 窗口按了退出键，stream 线程结束。
    pthread_join(tid_stream, NULL);

    // ==========================================
    // 8. 【退出】清理现场
    // ==========================================
    puts("Exiting...");

    // 强制关闭其他还在跑的辅助线程
    pthread_cancel(tid_display);
    pthread_cancel(tid_temperature);
    pthread_cancel(tid_cmd);

    // 关闭相机硬件连接
    uvc_camera_close();

    puts("Bye!");
    getchar(); 
    return 0;
}