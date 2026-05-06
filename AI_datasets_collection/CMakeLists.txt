cmake_minimum_required(VERSION 3.10)
project(SaperaCapture)

set(CMAKE_CXX_STANDARD 17)

# Define Sapera Paths (Adjust if your installation path is different)
set(SAPERA_CLASSES "D:/Classes/Basic")
set(SAPERA_INCLUDE "D:/Include")
set(SAPERA_LIB_DIR "D:/Lib/Win64")

include_directories(${SAPERA_CLASSES})
include_directories(${SAPERA_INCLUDE})

link_directories(${SAPERA_LIB_DIR})

file(GLOB SAPERA_CLASS_SOURCES "${SAPERA_CLASSES}/*.cpp")
add_executable(SaperaCapture main.cpp)

# Link the Sapera library
target_link_libraries(SaperaCapture SapClassBasic)

