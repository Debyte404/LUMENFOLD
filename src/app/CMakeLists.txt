add_executable(caustics_demo main.cpp)
add_executable(parity parity_main.cpp)
add_executable(dump dump_main.cpp)
add_executable(edt edt.cpp)  # standalone CDT-vs-scipy test (tools/edt_debug.py)
add_executable(bench bench_main.cpp)  # baker timing: geometric vs wave split
target_link_libraries(bench PRIVATE caustic)
# offline still renderer (pure CPU stdlib, no Filament/MuJoCo)
add_executable(showcase showcase_main.cpp)
target_compile_options(showcase PRIVATE /std:c++20 /EHsc /O2)
target_link_libraries(parity PRIVATE caustic)
target_link_libraries(dump PRIVATE caustic)

# ---- Path A offscreen viewer: MuJoCo + Filament (md variant, /MD) ----
set(FILAMENT_DIR "${CMAKE_SOURCE_DIR}/third_party/filament-1.77.2" CACHE PATH "Filament prebuilt root")
add_executable(viewer_offscreen viewer_offscreen.cpp stl_shim.cpp)
target_include_directories(viewer_offscreen PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}
  "${FILAMENT_DIR}/include" "${MUJOCO_DIR}/include")
target_link_directories(viewer_offscreen PRIVATE
  "${FILAMENT_DIR}/lib/x86_64/md" "${MUJOCO_DIR}/lib")
# /MD to match two_medium/caustic libs (default); use md-variant prebuilts
set_property(TARGET viewer_offscreen PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreadedDLL")
target_compile_options(viewer_offscreen PRIVATE /std:c++20 /EHsc)
target_compile_definitions(viewer_offscreen PRIVATE _CRT_SECURE_NO_WARNINGS)
target_link_libraries(viewer_offscreen PRIVATE two_medium caustic mujoco
  filament backend bluegl bluevk filabridge filaflat utils geometry smol-v ibl zstd abseil
  gdi32 user32 opengl32)

# ---- Path B interactive viewer: Win32 window + native SwapChain ----
add_executable(viewer_interactive WIN32 viewer_interactive.cpp stl_shim.cpp)
target_include_directories(viewer_interactive PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}
  "${FILAMENT_DIR}/include" "${MUJOCO_DIR}/include")
target_link_directories(viewer_interactive PRIVATE
  "${FILAMENT_DIR}/lib/x86_64/md" "${MUJOCO_DIR}/lib")
set_property(TARGET viewer_interactive PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreadedDLL")
target_compile_options(viewer_interactive PRIVATE /std:c++20 /EHsc)
target_compile_definitions(viewer_interactive PRIVATE _CRT_SECURE_NO_WARNINGS NOMINMAX WIN32_LEAN_AND_MEAN)
target_link_libraries(viewer_interactive PRIVATE two_medium caustic mujoco
  filament backend bluegl bluevk filabridge filaflat utils geometry smol-v ibl zstd abseil
  gdi32 user32 opengl32)
