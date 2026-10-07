cmake_minimum_required(VERSION 3.21)
project(caustics VERSION 0.1.0 LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Prebuilt drops live in third_party/ (see tools/fetch_third_party.sh).
set(MUJOCO_DIR "${CMAKE_SOURCE_DIR}/third_party/mujoco-3.14.0" CACHE PATH "MuJoCo prebuilt root")

add_subdirectory(src/physics)
add_subdirectory(src/render)
add_subdirectory(src/app)
