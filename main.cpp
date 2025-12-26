#include "OV9281_Driver.h"
#include "SimulatedEvent.h"
#include <iostream>

int main() {
    OV9281_Driver camera;
    SimulatedEvent ev_sim(0.40);

    while (true) {
        int choice;
        std::cout << "\n=== 4DGS 采集控制台 ===\n";
        std::cout << "1. 120FPS (1280x800) - 远景\n";
        std::cout << "2. 210FPS (640x400) - 标准 (最丝滑)\n";
        std::cout << "3. 420FPS (320x240) - 极限\n";
        std::cout << "4. 退出程序\n";
        std::cout << "请输入编号并回车: ";
        std::cin >> choice;

        if (choice == 4) break;

        int fps = (choice == 1) ? 120 : (choice == 2) ? 210 : 420;

        // 重新初始化相机
        camera.stop();
        if (!camera.init(0, fps)) {
            std::cout << "初始化失败，请检查连接！" << std::endl;
            continue;
        }
        camera.start();

        std::cout << "正在运行... 按 ESC 键回到菜单" << std::endl;

        cv::Mat raw, events;
        while (true) {
            if (camera.getFrame(raw)) {
                events = ev_sim.processFrame(raw);
                cv::imshow("Physical Event Stream", events);
            }
            if (cv::waitKey(1) == 27) { // 按 ESC 退出当前实时预览，回到输入菜单
                cv::destroyAllWindows();
                break;
            }
        }
    }
    return 0;
}