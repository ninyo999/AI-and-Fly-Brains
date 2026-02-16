#include <iostream>
#include <string>
#include <chrono>
#include <filesystem> 
#include "SapClassBasic.h"

namespace fs = std::filesystem;

void XferCallback(SapXferCallbackInfo *pInfo) {
    int index = pInfo->GetEventCount();
}

std::string GetTimestamp() {
    auto now = std::chrono::system_clock::now();
    std::time_t now_c = std::chrono::system_clock::to_time_t(now);
    struct tm timeinfo;
    localtime_s(&timeinfo, &now_c); // Safe version for MSVC
    char buf[100];
    std::strftime(buf, sizeof(buf), "%Y%m%d_%H%M%S", &timeinfo);
    return std::string(buf);
}

int main() {

    std::string folderName = "Run_" + GetTimestamp();
    fs::create_directory(folderName);
    std::cout << "Saving all data to folder: " << folderName << std::endl;

    SapLocation loc("Xtium-CL_MX4_1", 0);
    SapAcquisition acq(loc, "D:/CamFiles/User/AIandFlyBrains_camconfig.ccf");

    int numFrames = 30;
    SapBuffer buf(numFrames, &acq);
    SapTransfer xfer(XferCallback);
    xfer.AddPair(SapXferPair(&acq, &buf));

    if (!acq.Create() || !buf.Create() || !xfer.Create()) return -1;

    // Capture Sequence to RAM
    std::cout << "Grabbing " << numFrames << " frames..." << std::endl;
    xfer.Snap(numFrames);
    
    if (xfer.Wait(10000)) {
        std::cout << "Capture successful. Writing files..." << std::endl;

        int savedCount = 0;
        for (int i = 0; i < numFrames; i++) {
            // Changed extension to .bmp
            std::string filePath = folderName + "/frame_" + std::to_string(i) + ".bmp";
            
            // Changed format flag to "-format bmp"
            if (buf.Save(filePath.c_str(), "-format bmp", i)) {
                savedCount++;
            } else {
                std::cerr << "Failed to save frame " << i << std::endl;
            }
        }
        std::cout << "Done!" << std::endl;
    } else {
        std::cerr << "Capture Timeout." << std::endl;
    }

    xfer.Destroy(); buf.Destroy(); acq.Destroy();
    return 0;
}