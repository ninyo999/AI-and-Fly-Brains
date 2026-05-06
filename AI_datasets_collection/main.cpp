#include <iostream>
#include <string>
#include <chrono>
#include <filesystem>
#include <windows.h>
#include "SapClassBasic.h"

namespace fs = std::filesystem;

// To set folder nmae using time stamp
std::string GetTimestamp() {
    auto now = std::chrono::system_clock::now();
    std::time_t now_c = std::chrono::system_clock::to_time_t(now);
    struct tm timeinfo;
    localtime_s(&timeinfo, &now_c);
    char buf[100];
    std::strftime(buf, sizeof(buf), "%Y%m%d_%H%M%S", &timeinfo);
    return std::string(buf);
}

bool TriggerArduinoDebug(const std::string& portName) {
    std::cout << "Connecting to " << portName << "..." << std::endl;

    HANDLE hSerial = CreateFileA(portName.c_str(), GENERIC_READ | GENERIC_WRITE, 0, 0, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, 0);

    if (hSerial == INVALID_HANDLE_VALUE) {
        std::cerr << "CATCH: Could not open COM port. Error: " << GetLastError() << std::endl;
        return false;
    }

    DCB dcbSerialParams = { 0 };
    dcbSerialParams.DCBlength = sizeof(dcbSerialParams);
    GetCommState(hSerial, &dcbSerialParams);

    dcbSerialParams.BaudRate = CBR_9600;
    dcbSerialParams.ByteSize = 8;
    dcbSerialParams.StopBits = ONESTOPBIT;
    dcbSerialParams.Parity = NOPARITY;

    // enable DTR and RTS
    dcbSerialParams.fDtrControl = DTR_CONTROL_ENABLE;
    dcbSerialParams.fRtsControl = RTS_CONTROL_ENABLE;

    if (!SetCommState(hSerial, &dcbSerialParams)) {
        std::cerr << "CATCH: Could not set Serial parameters." << std::endl;
        CloseHandle(hSerial);
        return false;
    }

    // Wait for Arduino
    std::cout << "Port opened. Waiting 3s for Arduino reset..." << std::endl;
    Sleep(3000);

    const char* signal = "G";
    DWORD bytesWritten;
    if (WriteFile(hSerial, signal, 1, &bytesWritten, NULL)) {
        std::cout << "Signal 'G' written to buffer..." << std::endl;
    }

    FlushFileBuffers(hSerial);
    Sleep(100);
    CloseHandle(hSerial);
    std::cout << "Success" << std::endl;
    return true;
}

int main() {
    // Configuration
    int numFrames = 1050;
    std::string comPort = "\\\\.\\COM5";
    std::string folderName = "D:/datasets/Exp_" + GetTimestamp();
    fs::create_directories(folderName);

    // Hardware Setup
    SapLocation loc("Xtium-CL_MX4_1", 0);
    SapAcquisition acq(loc, "D:/CamFiles/User/AI_and_FlyBrains.ccf");
    SapBuffer buf(numFrames, &acq);
    SapTransfer xfer(NULL);
    xfer.AddPair(SapXferPair(&acq, &buf));

    if (!acq.Create() || !buf.Create() || !xfer.Create()) return -1;

    // Experiment Trigger
    if (!TriggerArduinoDebug(comPort)) {
        std::cerr << "Experiment aborted due to Trigger failure." << std::endl;
        return -1;
    }

    std::cout << "Capturing 1050 frames (35 seconds)..." << std::endl;
    auto startRAM = std::chrono::high_resolution_clock::now(); // Define missing startRAM
    xfer.Snap(numFrames);

    // Wait for Capture and Save
    if (xfer.Wait(40000)) {
        auto endRAM = std::chrono::high_resolution_clock::now();
        std::cout << "RAM Capture Time: " << std::chrono::duration<double>(endRAM - startRAM).count() << "s" << std::endl;

        std::cout << "Saving files to " << folderName << "..." << std::endl;
        auto startDisk = std::chrono::high_resolution_clock::now();

        for (int i = 0; i < numFrames; i++) {
            std::string path = folderName + "/frame_" + std::to_string(i) + ".tif";
            buf.Save(path.c_str(), "-format tif", i);
        }

        auto endDisk = std::chrono::high_resolution_clock::now();
        uintmax_t size = fs::file_size(folderName + "/frame_0.tif");
        double totalMB = (size * numFrames) / (1024.0 * 1024.0);

        std::cout << "Disk Write Speed:  " << (totalMB / std::chrono::duration<double>(endDisk - startDisk).count()) << " MB/s" << std::endl;
    } else {
        std::cerr << "Capture Timeout: Camera did not send frames." << std::endl;
    }

    // Cleanup
    xfer.Destroy();
    buf.Destroy();
    acq.Destroy();

    return 0;
}
