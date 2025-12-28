cmake_minimum_required(VERSION 3.10)
project(4D_System_Pi)

# 设置 C++ 标准
set(CMAKE_CXX_STANDARD 11)

# 1. 寻找树莓派 OpenCV
find_package(OpenCV REQUIRED)

# 2. 指定头文件路径 (包含 SDK 接口)
include_directories(
    ${CMAKE_SOURCE_DIR}
    ${CMAKE_SOURCE_DIR}/SDK/include
)

# 3. 指定动态库查找路径
link_directories(${CMAKE_SOURCE_DIR}/SDK/lib_linux)

# 4. 定义可执行程序及其包含的所有源码文件
add_executable(4D_System_Pi 
    main.cpp 
    sample.cpp
    OV9281_Driver.cpp 
    SimulatedEvent.cpp
    camera.cpp
    cmd.cpp
    data.cpp
    display.cpp
    temperature.cpp
)

# 5. 链接所有库
# 注意：库名不需要 lib 前缀和 .so 后缀
target_link_libraries(4D_System_Pi 
    ${OpenCV_LIBRARIES} 
    irparse irprocess irtemp iruvc usb-1.0
    pthread
)