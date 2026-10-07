add_library(caustic STATIC caustic.cpp caustic.hpp)
target_include_directories(caustic PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
