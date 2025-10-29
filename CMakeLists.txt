cmake_minimum_required(VERSION 3.12)
project(RotatingTriangles LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(OpenGL REQUIRED)
find_package(GLUT REQUIRED)

add_executable(triangle_demo src/main.cpp)

target_link_libraries(triangle_demo PRIVATE OpenGL::GL GLUT::GLUT)

target_compile_definitions(triangle_demo PRIVATE $<$<BOOL:${FREEGLUT_FOUND}>:FREEGLUT>)
