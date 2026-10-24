cmake_minimum_required(VERSION 3.16)
project(FleetSimEngine LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_executable(simulator
    src/main.cpp
    src/SimulationEngine.cpp
)

target_include_directories(simulator PRIVATE
    ${CMAKE_SOURCE_DIR}/include
    ${CMAKE_SOURCE_DIR}/third_party
)

set_target_properties(simulator PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}
    RUNTIME_OUTPUT_DIRECTORY_DEBUG ${CMAKE_BINARY_DIR}
    RUNTIME_OUTPUT_DIRECTORY_RELEASE ${CMAKE_BINARY_DIR}
    RUNTIME_OUTPUT_DIRECTORY_RELWITHDEBINFO ${CMAKE_BINARY_DIR}
    RUNTIME_OUTPUT_DIRECTORY_MINSIZEREL ${CMAKE_BINARY_DIR}
)

if(MSVC)
    target_compile_options(simulator PRIVATE /W4)
else()
    target_compile_options(simulator PRIVATE -Wall -Wextra -Wpedantic)
endif()

if(MINGW)
    target_link_options(simulator PRIVATE -static-libgcc -static-libstdc++ -static)
endif()
