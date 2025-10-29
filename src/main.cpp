#include <GL/glut.h>
#ifdef FREEGLUT
#include <GL/freeglut_ext.h>
#endif

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

namespace
{
struct DemoConfig
{
    int triangleCount = 1;
    bool benchmark = false;
    int benchmarkDurationMs = 10000;
    bool quiet = false;
};

struct Color
{
    float r;
    float g;
    float b;
};

DemoConfig g_config{};
float g_angleDegrees = 0.0f;
std::chrono::steady_clock::time_point g_lastFrameTime;
std::chrono::steady_clock::time_point g_lastFpsSample;
std::chrono::steady_clock::time_point g_benchmarkStart;
int g_frameCounter = 0;
int g_windowId = 0;
double g_fpsAccumulator = 0.0;
int g_fpsSamples = 0;
bool g_benchmarkFinished = false;
std::vector<Color> g_palette;

constexpr float kBaseTriangleRadius = 0.15f;
constexpr float kTriangleRingRadius = 0.55f;

float toDegrees(float radians)
{
    return radians * 180.0f / static_cast<float>(M_PI);
}

void ensurePaletteSize(std::size_t count)
{
    if (g_palette.size() >= count)
    {
        return;
    }

    g_palette.reserve(count);
    for (std::size_t i = g_palette.size(); i < count; ++i)
    {
        const float t = static_cast<float>(i) / std::max<std::size_t>(1, count - 1);
        const float hue = std::fmod(t * 360.0f, 360.0f);
        const float rad = hue * static_cast<float>(M_PI) / 180.0f;
        const float r = 0.5f + 0.5f * std::cos(rad);
        const float g = 0.5f + 0.5f * std::cos(rad + 2.0f * static_cast<float>(M_PI) / 3.0f);
        const float b = 0.5f + 0.5f * std::cos(rad + 4.0f * static_cast<float>(M_PI) / 3.0f);
        g_palette.push_back(Color{r, g, b});
    }
}

void updateWindowTitle(double fps)
{
#ifdef FREEGLUT
    std::ostringstream oss;
    oss << "Rotating Triangles - N=" << g_config.triangleCount;
    if (fps > 0.0)
    {
        oss << " | FPS=" << std::fixed << std::setprecision(1) << fps;
    }

    glutSetWindowTitle(oss.str().c_str());
#else
    (void)fps;
#endif
}

void finalizeBenchmark()
{
    if (g_benchmarkFinished)
    {
        return;
    }

    g_benchmarkFinished = true;
    double averageFps = (g_fpsSamples > 0) ? (g_fpsAccumulator / static_cast<double>(g_fpsSamples)) : 0.0;
    std::cout << "FPS_RESULT triangles=" << g_config.triangleCount << ",avg_fps=" << averageFps << std::endl;
    std::cout.flush();
}

void drawTriangle(float offsetAngleRadians, const Color &color)
{
    glPushMatrix();

    const float x = kTriangleRingRadius * std::cos(offsetAngleRadians);
    const float y = kTriangleRingRadius * std::sin(offsetAngleRadians);
    glTranslatef(x, y, 0.0f);

    glRotatef(g_angleDegrees * 1.5f + toDegrees(offsetAngleRadians), 0.0f, 0.0f, 1.0f);

    glColor3f(color.r, color.g, color.b);

    glBegin(GL_TRIANGLES);
    glVertex2f(0.0f, kBaseTriangleRadius);
    glVertex2f(-kBaseTriangleRadius, -kBaseTriangleRadius);
    glVertex2f(kBaseTriangleRadius, -kBaseTriangleRadius);
    glEnd();

    glPopMatrix();
}

void display()
{
    const auto now = std::chrono::steady_clock::now();
    if (g_lastFrameTime.time_since_epoch().count() == 0)
    {
        g_lastFrameTime = now;
        g_lastFpsSample = now;
        g_benchmarkStart = now;
    }

    glClearColor(0.05f, 0.05f, 0.08f, 1.0f);
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);

    glMatrixMode(GL_MODELVIEW);
    glLoadIdentity();

    ensurePaletteSize(static_cast<std::size_t>(g_config.triangleCount));

    const float angleStep = (g_config.triangleCount > 1) ? (2.0f * static_cast<float>(M_PI) / g_config.triangleCount) : 0.0f;
    for (int i = 0; i < g_config.triangleCount; ++i)
    {
        const float offset = static_cast<float>(i) * angleStep;
        drawTriangle(offset, g_palette[static_cast<std::size_t>(i)]);
    }

    glutSwapBuffers();

    ++g_frameCounter;
    const double secondsSinceSample = std::chrono::duration<double>(now - g_lastFpsSample).count();
    if (secondsSinceSample >= 1.0)
    {
        const double fps = static_cast<double>(g_frameCounter) / secondsSinceSample;
        if (!g_config.quiet)
        {
            updateWindowTitle(fps);
        }

        g_fpsAccumulator += fps;
        ++g_fpsSamples;
        g_frameCounter = 0;
        g_lastFpsSample = now;

        if (g_config.benchmark && g_config.quiet)
        {
            std::cout << "FPS_SAMPLE triangles=" << g_config.triangleCount << ",fps=" << fps << std::endl;
            std::cout.flush();
        }
    }
}

void idle()
{
    const auto now = std::chrono::steady_clock::now();
    const float delta = std::chrono::duration<float>(now - g_lastFrameTime).count();
    g_lastFrameTime = now;

    const float rotationSpeedDegreesPerSecond = 60.0f;
    g_angleDegrees = std::fmod(g_angleDegrees + rotationSpeedDegreesPerSecond * delta, 360.0f);

    if (g_config.benchmark)
    {
        const auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(now - g_benchmarkStart);
        if (elapsed.count() >= g_config.benchmarkDurationMs)
        {
            finalizeBenchmark();
#ifdef FREEGLUT
            glutLeaveMainLoop();
#else
            std::exit(EXIT_SUCCESS);
#endif
            return;
        }
    }

    glutPostRedisplay();
}

void reshape(int width, int height)
{
    glViewport(0, 0, width, height);
    glMatrixMode(GL_PROJECTION);
    glLoadIdentity();

    const float aspect = static_cast<float>(width) / static_cast<float>(height > 0 ? height : 1);
    if (aspect >= 1.0f)
    {
        glOrtho(-aspect, aspect, -1.0f, 1.0f, -1.0f, 1.0f);
    }
    else
    {
        glOrtho(-1.0f, 1.0f, -1.0f / aspect, 1.0f / aspect, -1.0f, 1.0f);
    }

    glMatrixMode(GL_MODELVIEW);
}

void parseArguments(int argc, char **argv)
{
    for (int i = 1; i < argc; ++i)
    {
        const std::string arg = argv[i];
        if (arg == "--triangles" && i + 1 < argc)
        {
            g_config.triangleCount = std::max(1, std::atoi(argv[++i]));
        }
        else if (arg == "--benchmark")
        {
            g_config.benchmark = true;
            g_config.quiet = true;
        }
        else if (arg == "--duration" && i + 1 < argc)
        {
            g_config.benchmarkDurationMs = std::max(1, std::atoi(argv[++i])) * 1000;
        }
        else if (arg == "--show-log")
        {
            g_config.quiet = false;
        }
        else if (arg == "--help")
        {
            std::cout << "Rotating triangle demo using GLUT" << std::endl;
            std::cout << "Options:\n"
                      << "  --triangles <N>   Number of triangles to render (default 1)\n"
                      << "  --benchmark       Enable benchmark mode (non-interactive)\n"
                      << "  --duration <s>    Benchmark duration in seconds (default 10)\n"
                      << "  --show-log        Keep FPS logging on stdout during benchmark\n"
                      << "  --help            Show this message\n";
            std::exit(EXIT_SUCCESS);
        }
    }
}

} // namespace

int main(int argc, char **argv)
{
    parseArguments(argc, argv);

    glutInit(&argc, argv);
    glutInitDisplayMode(GLUT_DOUBLE | GLUT_RGB | GLUT_DEPTH);
    glutInitWindowSize(800, 600);
    g_windowId = glutCreateWindow("Rotating Triangles");

#ifdef FREEGLUT
    glutSetOption(GLUT_ACTION_ON_WINDOW_CLOSE, GLUT_ACTION_GLUTMAINLOOP_RETURNS);
#endif

    glutDisplayFunc(display);
    glutIdleFunc(idle);
    glutReshapeFunc(reshape);

    glDisable(GL_DEPTH_TEST);

    g_lastFrameTime = std::chrono::steady_clock::now();
    g_lastFpsSample = g_lastFrameTime;
    g_benchmarkStart = g_lastFrameTime;

    glutMainLoop();

    finalizeBenchmark();
    return 0;
}
