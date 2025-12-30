#include "OV9281_Driver.h"
#include <iostream>
#include <fcntl.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <linux/videodev2.h>
#include <cstring>
#include <chrono>

OV9281_Driver::OV9281_Driver() : fd(-1), is_running(false), has_new_frame(false), n_buffers(0) {}
OV9281_Driver::~OV9281_Driver() { stop(); }

// 辅助：设置 V4L2 参数
int OV9281_Driver::set_control(int id, int value) {
    struct v4l2_control ctrl;
    ctrl.id = id;
    ctrl.value = value;
    if (ioctl(fd, VIDIOC_S_CTRL, &ctrl) == -1) {
        perror("set_control");
        return -1;
    }
    return 0;
}

bool OV9281_Driver::init(int camera_id, int target_fps) {
    std::string dev_name = "/dev/video" + std::to_string(camera_id);
    fd = open(dev_name.c_str(), O_RDWR | O_NONBLOCK, 0);
    if (fd == -1) {
        std::cerr << "[Error] Cannot open device " << dev_name << std::endl;
        return false;
    }

    // 1. 设置格式: MJPG, 1280x800
    struct v4l2_format fmt;
    memset(&fmt, 0, sizeof(fmt));
    fmt.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    fmt.fmt.pix.width = 1280;
    fmt.fmt.pix.height = 800;
    fmt.fmt.pix.pixelformat = V4L2_PIX_FMT_MJPEG; // 关键：获取压缩流
    fmt.fmt.pix.field = V4L2_FIELD_ANY;
    if (ioctl(fd, VIDIOC_S_FMT, &fmt) == -1) {
        perror("VIDIOC_S_FMT");
        return false;
    }

    // 2. 设置帧率 120FPS
    struct v4l2_streamparm streamparm;
    memset(&streamparm, 0, sizeof(streamparm));
    streamparm.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    streamparm.parm.capture.timeperframe.numerator = 1;
    streamparm.parm.capture.timeperframe.denominator = 120;
    if (ioctl(fd, VIDIOC_S_PARM, &streamparm) == -1) {
        perror("VIDIOC_S_PARM");
    }

    // 3. 申请缓冲区
    struct v4l2_requestbuffers req;
    memset(&req, 0, sizeof(req));
    req.count = 4; // 4个缓冲队列
    req.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    req.memory = V4L2_MEMORY_MMAP;
    if (ioctl(fd, VIDIOC_REQBUFS, &req) == -1) return false;

    buffers.resize(req.count);
    for (size_t i = 0; i < req.count; ++i) {
        struct v4l2_buffer buf;
        memset(&buf, 0, sizeof(buf));
        buf.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
        buf.memory = V4L2_MEMORY_MMAP;
        buf.index = i;
        if (ioctl(fd, VIDIOC_QUERYBUF, &buf) == -1) return false;

        buffers[i].length = buf.length;
        buffers[i].start = mmap(NULL, buf.length, PROT_READ | PROT_WRITE, MAP_SHARED, fd, buf.m.offset);
        if (buffers[i].start == MAP_FAILED) return false;
    }

    // 4. 入队缓冲区
    for (size_t i = 0; i < req.count; ++i) {
        struct v4l2_buffer buf;
        memset(&buf, 0, sizeof(buf));
        buf.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
        buf.memory = V4L2_MEMORY_MMAP;
        buf.index = i;
        if (ioctl(fd, VIDIOC_QBUF, &buf) == -1) return false;
    }

    // 5. 硬件参数配置 (防闪烁, 曝光, 增益)
    set_control(V4L2_CID_POWER_LINE_FREQUENCY, V4L2_CID_POWER_LINE_FREQUENCY_DISABLED);
    set_control(V4L2_CID_EXPOSURE_AUTO, V4L2_EXPOSURE_MANUAL);
    set_control(V4L2_CID_EXPOSURE_ABSOLUTE, 20); // 2ms
    set_control(V4L2_CID_GAIN, 200);

    // 6. 开始推流
    enum v4l2_buf_type type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    if (ioctl(fd, VIDIOC_STREAMON, &type) == -1) return false;

    std::cout << ">>> [Driver] V4L2 Native Driver Initialized (MJPG @ 120FPS)" << std::endl;
    return true;
}

void OV9281_Driver::start() {
    is_running = true;
    worker = std::thread(&OV9281_Driver::capture_loop, this);
}

void OV9281_Driver::stop() {
    is_running = false;
    if (worker.joinable()) worker.join();
    
    // 清理资源
    enum v4l2_buf_type type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    ioctl(fd, VIDIOC_STREAMOFF, &type);
    for (size_t i = 0; i < buffers.size(); ++i) {
        munmap(buffers[i].start, buffers[i].length);
    }
    if (fd != -1) close(fd);
}

void OV9281_Driver::capture_loop() {
    uint32_t frame_counter = 0;
    struct v4l2_buffer buf;
    
    while (is_running) {
        fd_set fds;
        FD_ZERO(&fds);
        FD_SET(fd, &fds);
        struct timeval tv = {2, 0}; // 2秒超时
        
        int r = select(fd + 1, &fds, NULL, NULL, &tv);
        if (r <= 0) continue;

        memset(&buf, 0, sizeof(buf));
        buf.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
        buf.memory = V4L2_MEMORY_MMAP;
        
        // 出队
        if (ioctl(fd, VIDIOC_DQBUF, &buf) == -1) continue;

        // 获取时间戳
        struct timeval sys_time;
        gettimeofday(&sys_time, NULL);
        uint64_t timestamp = (uint64_t)sys_time.tv_sec * 1000000 + sys_time.tv_usec;

        // 拷贝压缩数据到本地存储 (准备发送)
        {
            std::lock_guard<std::mutex> lock(mtx);
            // 只需要拷贝有效数据长度 buf.bytesused
            if (latest_packet.data.capacity() < buf.bytesused) {
                latest_packet.data.reserve(buf.bytesused + 1024);
            }
            latest_packet.data.resize(buf.bytesused);
            memcpy(latest_packet.data.data(), buffers[buf.index].start, buf.bytesused);
            latest_packet.timestamp_us = timestamp;
            latest_packet.frame_id = frame_counter++;
            has_new_frame = true;
        }

        // 重新入队
        ioctl(fd, VIDIOC_QBUF, &buf);
    }
}

bool OV9281_Driver::getLatestRawFrame(RawDataPacket& packet) {
    std::lock_guard<std::mutex> lock(mtx);
    if (!has_new_frame) return false;
    packet = latest_packet; // 内存拷贝，但 MJPG 一帧通常只有 100KB-200KB，速度很快
    has_new_frame = false;
    return true;
}