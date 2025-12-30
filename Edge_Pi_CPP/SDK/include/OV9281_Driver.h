#ifndef OV9281_DRIVER_H
#define OV9281_DRIVER_H

#include <vector>
#include <thread>
#include <mutex>
#include <atomic>
#include <sys/time.h>

// 定义数据包结构体用于回调或获取
struct RawDataPacket {
    std::vector<unsigned char> data;
    uint64_t timestamp_us;
    uint32_t frame_id;
};

class OV9281_Driver {
public:
    OV9281_Driver();
    ~OV9281_Driver();

    bool init(int camera_id, int target_fps);
    void start();
    void stop();
    
    // 获取最新的一帧原始 MJPG 数据（线程安全，用于发送）
    bool getLatestRawFrame(RawDataPacket& packet);

private:
    void capture_loop();
    int set_control(int id, int value); // V4L2 控制辅助函数

    int fd; // 设备文件描述符
    std::atomic<bool> is_running;
    std::thread worker;
    std::mutex mtx;
    
    RawDataPacket latest_packet;
    bool has_new_frame;

    struct Buffer {
        void *start;
        size_t length;
    };
    std::vector<Buffer> buffers;
    int n_buffers;
};

#endif