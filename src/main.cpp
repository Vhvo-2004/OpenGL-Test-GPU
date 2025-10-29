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
enum class LightingMode
{
    None,
    Point,
    Spot,
    PointAndSpot
};

struct DemoConfig
{
    int triangleCount = 1;
    bool benchmark = false;
    int benchmarkDurationMs = 10000;
    bool quiet = false;
    bool textured = true;
    LightingMode lighting = LightingMode::None;
};

struct Color
{
    float r;
    float g;
    float b;
};

DemoConfig g_config{};
float g_angleDegrees = 0.0f;
std::chrono::steady_clock::time_point g_lastFrameTime{};
std::chrono::steady_clock::time_point g_lastFpsSample{};
std::chrono::steady_clock::time_point g_benchmarkStart{};
int g_frameCounter = 0;
int g_windowId = 0;
double g_fpsAccumulator = 0.0;
int g_fpsSamples = 0;
bool g_benchmarkFinished = false;
std::vector<Color> g_palette;
GLuint g_textureId = 0;
bool g_textureReady = false;

constexpr float kBaseTriangleRadius = 0.15f;
constexpr float kTriangleHeight = kBaseTriangleRadius * std::sqrt(3.0f);
constexpr float kTriangleRingRadius = 0.55f;

float toDegrees(float radians)
{
    return radians * 180.0f / static_cast<float>(M_PI);
}

std::string lightingModeToString(LightingMode mode)
{
    switch (mode)
    {
    case LightingMode::Point:
        return "point";
    case LightingMode::Spot:
        return "spot";
    case LightingMode::PointAndSpot:
        return "both";
    case LightingMode::None:
    default:
        return "none";
    }
}

LightingMode parseLightingMode(const std::string &value)
{
    if (value == "point")
    {
        return LightingMode::Point;
    }
    if (value == "spot")
    {
        return LightingMode::Spot;
    }
    if (value == "both" || value == "point_spot" || value == "pointandspot")
    {
        return LightingMode::PointAndSpot;
    }
    return LightingMode::None;
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
        const float r = 0.6f + 0.4f * std::cos(rad);
        const float g = 0.6f + 0.4f * std::cos(rad + 2.0f * static_cast<float>(M_PI) / 3.0f);
        const float b = 0.6f + 0.4f * std::cos(rad + 4.0f * static_cast<float>(M_PI) / 3.0f);
        g_palette.push_back(Color{r, g, b});
    }
}

void updateWindowTitle(double fps)
{
#ifdef FREEGLUT
    std::ostringstream oss;
    oss << "Rotating Triangles - N=" << g_config.triangleCount;
    oss << " | lighting=" << lightingModeToString(g_config.lighting);
    oss << (g_config.textured ? " | textured" : " | flat");
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
    std::cout << "FPS_RESULT triangles=" << g_config.triangleCount
              << ",lighting=" << lightingModeToString(g_config.lighting)
              << ",textured=" << (g_config.textured ? 1 : 0)
              << ",avg_fps=" << averageFps << std::endl;
    std::cout.flush();
}

void ensureTexture()
{
    if (g_textureReady)
    {
        return;
    }

    constexpr int size = 128;
    constexpr int block = 16;
    std::vector<unsigned char> data(static_cast<std::size_t>(size * size * 3));

    for (int y = 0; y < size; ++y)
    {
        for (int x = 0; x < size; ++x)
        {
            const bool bright = ((x / block) + (y / block)) % 2 == 0;
            const float gradient = static_cast<float>(y) / static_cast<float>(size - 1);
            const unsigned char base = static_cast<unsigned char>(bright ? 180 : 40);
            const unsigned char r = static_cast<unsigned char>(std::min(255.0f, base + 75.0f * gradient));
            const unsigned char g = static_cast<unsigned char>(std::min(255.0f, base + 40.0f * (1.0f - gradient)));
            const unsigned char b = static_cast<unsigned char>(std::min(255.0f, base + 100.0f * (0.5f - std::fabs(0.5f - gradient))));

            const std::size_t index = static_cast<std::size_t>((y * size + x) * 3);
            data[index] = r;
            data[index + 1] = g;
            data[index + 2] = b;
        }
    }

    glGenTextures(1, &g_textureId);
    glBindTexture(GL_TEXTURE_2D, g_textureId);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT);
    glTexEnvi(GL_TEXTURE_ENV, GL_TEXTURE_ENV_MODE, GL_MODULATE);

    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, size, size, 0, GL_RGB, GL_UNSIGNED_BYTE, data.data());
    g_textureReady = true;
}

void applyLightingState()
{
    if (g_config.lighting == LightingMode::None)
    {
        glDisable(GL_LIGHTING);
        glDisable(GL_LIGHT0);
        glDisable(GL_LIGHT1);
        return;
    }

    glEnable(GL_LIGHTING);
    glEnable(GL_NORMALIZE);
    glEnable(GL_COLOR_MATERIAL);
    glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE);

    const GLfloat ambient[] = {0.15f, 0.15f, 0.18f, 1.0f};
    glLightModelfv(GL_LIGHT_MODEL_AMBIENT, ambient);

    const GLfloat pointPosition[] = {0.0f, 0.0f, 1.8f, 1.0f};
    const GLfloat spotPosition[] = {0.0f, 0.0f, 2.2f, 1.0f};
    const GLfloat spotDirection[] = {0.0f, 0.0f, -1.0f};
    const GLfloat pointDiffuse[] = {0.9f, 0.9f, 0.95f, 1.0f};
    const GLfloat spotDiffuse[] = {0.95f, 0.9f, 0.7f, 1.0f};

    if (g_config.lighting == LightingMode::Point)
    {
        glEnable(GL_LIGHT0);
        glDisable(GL_LIGHT1);
        glLightfv(GL_LIGHT0, GL_POSITION, pointPosition);
        glLightfv(GL_LIGHT0, GL_DIFFUSE, pointDiffuse);
        glLightfv(GL_LIGHT0, GL_SPECULAR, pointDiffuse);
    }
    else if (g_config.lighting == LightingMode::Spot)
    {
        glDisable(GL_LIGHT0);
        glEnable(GL_LIGHT1);
        glLightfv(GL_LIGHT1, GL_POSITION, spotPosition);
        glLightfv(GL_LIGHT1, GL_SPOT_DIRECTION, spotDirection);
        glLightf(GL_LIGHT1, GL_SPOT_CUTOFF, 32.0f);
        glLightf(GL_LIGHT1, GL_SPOT_EXPONENT, 12.0f);
        glLightfv(GL_LIGHT1, GL_DIFFUSE, spotDiffuse);
        glLightfv(GL_LIGHT1, GL_SPECULAR, spotDiffuse);
    }
    else
    {
        glEnable(GL_LIGHT0);
        glEnable(GL_LIGHT1);

        glLightfv(GL_LIGHT0, GL_POSITION, pointPosition);
        glLightfv(GL_LIGHT0, GL_DIFFUSE, pointDiffuse);
        glLightfv(GL_LIGHT0, GL_SPECULAR, pointDiffuse);

        glLightfv(GL_LIGHT1, GL_POSITION, spotPosition);
        glLightfv(GL_LIGHT1, GL_SPOT_DIRECTION, spotDirection);
        glLightf(GL_LIGHT1, GL_SPOT_CUTOFF, 32.0f);
        glLightf(GL_LIGHT1, GL_SPOT_EXPONENT, 12.0f);
        glLightfv(GL_LIGHT1, GL_DIFFUSE, spotDiffuse);
        glLightfv(GL_LIGHT1, GL_SPECULAR, spotDiffuse);
    }
}

void initializeRenderState()
{
    glDisable(GL_DEPTH_TEST);
    glShadeModel(GL_SMOOTH);
    glEnable(GL_BLEND);
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);

    if (g_config.textured)
    {
        ensureTexture();
        glEnable(GL_TEXTURE_2D);
        glBindTexture(GL_TEXTURE_2D, g_textureId);
    }
    else
    {
        glDisable(GL_TEXTURE_2D);
    }

    applyLightingState();
}

void drawTriangle(float offsetAngleRadians, const Color &color)
{
    glPushMatrix();

    const float x = kTriangleRingRadius * std::cos(offsetAngleRadians);
    const float y = kTriangleRingRadius * std::sin(offsetAngleRadians);
    glTranslatef(x, y, 0.0f);

    glRotatef(g_angleDegrees * 1.5f + toDegrees(offsetAngleRadians), 0.0f, 0.0f, 1.0f);

    glColor3f(color.r, color.g, color.b);

    if (g_config.textured)
    {
        glEnable(GL_TEXTURE_2D);
        glBindTexture(GL_TEXTURE_2D, g_textureId);
    }
    else
    {
        glDisable(GL_TEXTURE_2D);
    }

    const float topY = (2.0f / 3.0f) * kTriangleHeight;
    const float bottomY = -(1.0f / 3.0f) * kTriangleHeight;

    glBegin(GL_TRIANGLES);
    glNormal3f(0.0f, 0.0f, 1.0f);

    glTexCoord2f(0.5f, 1.0f);
    glVertex3f(0.0f, topY, 0.0f);

    glTexCoord2f(0.0f, 0.0f);
    glVertex3f(-kBaseTriangleRadius, bottomY, 0.0f);

    glTexCoord2f(1.0f, 0.0f);
    glVertex3f(kBaseTriangleRadius, bottomY, 0.0f);
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

    applyLightingState();

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
            std::cout << "FPS_SAMPLE triangles=" << g_config.triangleCount
                      << ",lighting=" << lightingModeToString(g_config.lighting)
                      << ",textured=" << (g_config.textured ? 1 : 0)
                      << ",fps=" << fps << std::endl;
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
        else if (arg == "--lighting" && i + 1 < argc)
        {
            g_config.lighting = parseLightingMode(argv[++i]);
        }
        else if (arg == "--no-texture")
        {
            g_config.textured = false;
        }
        else if (arg == "--help")
        {
            std::cout << "Rotating triangle demo using GLUT" << std::endl;
            std::cout << "Options:\n"
                      << "  --triangles <N>   Number of triangles to render (default 1)\n"
                      << "  --benchmark       Enable benchmark mode (non-interactive)\n"
                      << "  --duration <s>    Benchmark duration in seconds (default 10)\n"
                      << "  --show-log        Keep FPS logging on stdout during benchmark\n"
                      << "  --lighting <mode> Lighting mode: none, point, spot, both (default none)\n"
                      << "  --no-texture      Disable textured rendering\n"
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

    initializeRenderState();

    g_lastFrameTime = std::chrono::steady_clock::now();
    g_lastFpsSample = g_lastFrameTime;
    g_benchmarkStart = g_lastFrameTime;

    glutMainLoop();

    finalizeBenchmark();
    return 0;
}
