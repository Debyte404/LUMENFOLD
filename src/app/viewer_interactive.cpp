// viewer_interactive.cpp — Path B: Win32 window + Filament SwapChain(HWND).
// Live demo: orbit camera (drag), MuJoCo stepping with two_medium buoyancy,
// caustic texture re-baked every K frames for animated water.
// Controls: drag = orbit, wheel = zoom, space = pause, S = screenshot (PNG), Esc = quit.
#define NOMINMAX
#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <chrono>
#include <fstream>
#include <string>
#include <vector>

#include <filament/Engine.h>
#include <filament/Renderer.h>
#include <filament/Scene.h>
#include <filament/View.h>
#include <filament/Camera.h>
#include <filament/Material.h>
#include <filament/MaterialInstance.h>
#include <filament/RenderableManager.h>
#include <filament/TransformManager.h>
#include <filament/Texture.h>
#include <filament/TextureSampler.h>
#include <filament/VertexBuffer.h>
#include <filament/IndexBuffer.h>
#include <filament/SwapChain.h>
#include <filament/Viewport.h>
#include <filament/LightManager.h>
#include <backend/BufferDescriptor.h>
#include <backend/PixelBufferDescriptor.h>
#include <utils/EntityManager.h>
#include <math/mat4.h>
#include <math/vec3.h>

#include <mujoco/mujoco.h>

#include "two_medium.hpp"
#include "caustic.hpp"

// discrete GPU on hybrid laptops
extern "C" {
__declspec(dllexport) unsigned long NvOptimusEnablement = 1;
__declspec(dllexport) int AmdPowerXpressRequestHighPerformance = 1;
}

using namespace filament;
using namespace filament::math;

// ---------- PNG writer (shared pattern with offscreen viewer) ----------
namespace {
uint32_t crc_table[256];
bool crc_ready = false;
void crc_init() {
  for (uint32_t n = 0; n < 256; n++) {
    uint32_t c = n;
    for (int k = 0; k < 8; k++) c = (c & 1) ? (0xEDB88320u ^ (c >> 1)) : (c >> 1);
    crc_table[n] = c;
  }
  crc_ready = true;
}
uint32_t crc(const uint8_t* p, size_t n) {
  if (!crc_ready) crc_init();
  uint32_t c = 0xFFFFFFFFu;
  for (size_t i = 0; i < n; i++) c = crc_table[(c ^ p[i]) & 0xFF] ^ (c >> 8);
  return c ^ 0xFFFFFFFFu;
}
void put32(std::vector<uint8_t>& o, uint32_t v) {
  o.push_back((v >> 24) & 0xFF);
  o.push_back((v >> 16) & 0xFF);
  o.push_back((v >> 8) & 0xFF);
  o.push_back(v & 0xFF);
}
void chunk(std::vector<uint8_t>& o, const char* tag, const uint8_t* d, size_t n) {
  put32(o, (uint32_t)n);
  size_t h = o.size();
  o.insert(o.end(), tag, tag + 4);
  o.insert(o.end(), d, d + n);
  put32(o, crc(o.data() + h, 4 + n));
}
std::vector<uint8_t> zlib_store(const uint8_t* d, size_t n) {
  std::vector<uint8_t> o = {0x78, 0x01};
  uint32_t a = 1, b = 0;
  size_t i = 0;
  while (i < n) {
    size_t blk = std::min<size_t>(n - i, 65535);
    bool last = (i + blk == n);
    o.push_back(last ? 0x01 : 0x00);
    o.push_back(blk & 0xFF);
    o.push_back((blk >> 8) & 0xFF);
    o.push_back((~blk) & 0xFF);
    o.push_back(((~blk) >> 8) & 0xFF);
    o.insert(o.end(), d + i, d + i + blk);
    for (size_t k = i; k < i + blk; k++) {
      a += d[k];
      b += a;
      a %= 65521;
      b %= 65521;
    }
    i += blk;
  }
  put32(o, (b << 16) | a);
  return o;
}
bool write_png(const char* path, int W, int H, const std::vector<uint8_t>& rgb_topdown) {
  std::vector<uint8_t> o = {137, 80, 78, 71, 13, 10, 26, 10};
  uint8_t ihdr[13] = {(uint8_t)(W >> 24), (uint8_t)(W >> 16), (uint8_t)(W >> 8), (uint8_t)W,
                       (uint8_t)(H >> 24), (uint8_t)(H >> 16), (uint8_t)(H >> 8), (uint8_t)H,
                       8, 2, 0, 0, 0};
  chunk(o, "IHDR", ihdr, 13);
  std::vector<uint8_t> raw;
  raw.reserve((size_t)H * (W * 3 + 1));
  for (int y = 0; y < H; y++) {
    raw.push_back(0);
    raw.insert(raw.end(), rgb_topdown.begin() + (size_t)y * W * 3,
               rgb_topdown.begin() + (size_t)(y + 1) * W * 3);
  }
  auto z = zlib_store(raw.data(), raw.size());
  chunk(o, "IDAT", z.data(), z.size());
  chunk(o, "IEND", nullptr, 0);
  std::ofstream f(path, std::ios::binary);
  if (!f) return false;
  f.write((const char*)o.data(), o.size());
  return true;
}
std::vector<uint8_t> read_file(const char* path) {
  std::ifstream f(path, std::ios::binary | std::ios::ate);
  if (!f) return {};
  std::streamsize n = f.tellg();
  f.seekg(0);
  std::vector<uint8_t> o((size_t)n);
  f.read((char*)o.data(), n);
  return o;
}
}  // namespace

// ---------- app state ----------
struct App {
  bool quit = false;
  bool paused = false;
  bool want_shot = false;
  float yaw = -0.7f;    // orbit around pool center
  float pitch = 0.9f;   // elevation
  float dist = 8.0f;    // camera distance
  // Blender-style navigation: MMB orbits, Shift+MMB pans, wheel zooms
  float tx = 0.0f, ty = 0.0f, tz = -0.5f;  // camera target (pan moves this)
  bool orbit_drag = false;
  bool pan_drag = false;
  int last_x = 0, last_y = 0;
  // viewport toggles (Blender-ish: grid, shading mode, A/B compare)
  bool show_grid = true;
  bool use_wave = true;   // false = raw geometric quadrature
  bool split = true;      // left half geometric, right half wave-corrected
  int shot_wait = 0;      // frames to settle before an interactive screenshot
  float sim_time = 0;
  int frame = 0;
  // live stats for the title bar
  double bake_ms = 0.0;
  double bake_geo_ms = 0.0;
  double frame_ms = 0.0;
  float peak_geo = 0.0f, peak_wave = 0.0f;
};
static App g_app;

static float3 cam_eye() {
  return float3{std::sin(g_app.yaw) * std::cos(g_app.pitch) * g_app.dist,
                std::cos(g_app.yaw) * std::cos(g_app.pitch) * g_app.dist,
                std::sin(g_app.pitch) * g_app.dist};
}

static LRESULT CALLBACK wnd_proc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
  switch (msg) {
    case WM_DESTROY:
      g_app.quit = true;
      return 0;
    case WM_KEYDOWN:
      switch (wp) {
        case VK_ESCAPE: g_app.quit = true; break;
        case VK_SPACE: g_app.paused = !g_app.paused; break;
        case 'S': g_app.want_shot = true; break;
        // NB: lowercase aliases are unsafe here - VK_NUMPAD7 (0x67) == 'g',
        // VK_NUMPAD1 (0x61) == 'a', VK_NUMPAD3 (0x63) == 'c'.
        case 'G': g_app.show_grid = !g_app.show_grid; break;
        case 'B': g_app.use_wave = !g_app.use_wave; break;
        case 'X': g_app.split = !g_app.split; break;
        // Blender numpad views
        case '1': case VK_NUMPAD1: g_app.yaw = 0.0f; g_app.pitch = 0.06f; break;
        case '3': case VK_NUMPAD3: g_app.yaw = 1.5708f; g_app.pitch = 0.06f; break;
        case '7': case VK_NUMPAD7: g_app.yaw = 0.0f; g_app.pitch = 1.44f; break;
        case VK_HOME:
          g_app.yaw = -0.7f; g_app.pitch = 0.9f; g_app.dist = 8.0f;
          g_app.tx = 0.0f; g_app.ty = 0.0f; g_app.tz = -0.5f;
          break;
        default: break;
      }
      return 0;
    case WM_LBUTTONDOWN:
    case WM_MBUTTONDOWN: {
      bool shift = (GetKeyState(VK_SHIFT) & 0x8000) != 0;
      if (msg == WM_MBUTTONDOWN && shift) {
        g_app.pan_drag = true;
      } else {
        g_app.orbit_drag = true;
      }
      g_app.last_x = LOWORD(lp);
      g_app.last_y = HIWORD(lp);
      SetCapture(hwnd);
      return 0;
    }
    case WM_LBUTTONUP:
    case WM_MBUTTONUP:
      g_app.orbit_drag = false;
      g_app.pan_drag = false;
      ReleaseCapture();
      return 0;
    case WM_MOUSEMOVE: {
      int x = LOWORD(lp), y = HIWORD(lp);
      if (g_app.orbit_drag) {
        g_app.yaw += (x - g_app.last_x) * 0.005f;
        g_app.pitch = std::clamp(g_app.pitch + (y - g_app.last_y) * 0.005f, 0.02f, 1.45f);
      } else if (g_app.pan_drag) {
        // pan in the camera plane (Blender Shift+MMB)
        float cy = std::cos(g_app.yaw), sy = std::sin(g_app.yaw);
        float cp = std::cos(g_app.pitch), sp = std::sin(g_app.pitch);
        float3 fwd{-sy * cp, -cy * cp, -sp};   // eye -> target
        float3 right = normalize(float3{-cy, sy, 0.0f});
        float3 up = cross(right, fwd);
        float k = g_app.dist * 0.0016f;
        float dx = float(x - g_app.last_x) * k, dy = float(y - g_app.last_y) * k;
        g_app.tx += -right.x * dx + up.x * dy;
        g_app.ty += -right.y * dx + up.y * dy;
        g_app.tz += -right.z * dx + up.z * dy;
      }
      g_app.last_x = x;
      g_app.last_y = y;
      return 0;
    }
    case WM_MOUSEWHEEL:
      g_app.dist = std::clamp(g_app.dist - GET_WHEEL_DELTA_WPARAM(wp) * 0.002f, 1.0f, 40.0f);
      return 0;
  }
  return DefWindowProcA(hwnd, msg, wp, lp);
}

static twomed::Body body_from_mj(const mjData* d, int body_id, twomed::Shape shape,
                                 const double* p, double mass) {
  twomed::Body b;
  b.shape = shape;
  b.p = {p[0], p[1], p[2]};
  b.mass = mass;
  b.x = {d->xpos[body_id * 3 + 0], d->xpos[body_id * 3 + 1], d->xpos[body_id * 3 + 2]};
  mjtNum R9[9];
  mju_quat2Mat(R9, d->xquat + body_id * 4);
  for (int i = 0; i < 9; i++) b.R[i] = R9[i];
  return b;
}

// ---------- tiny mesh builders (positions + normals, no UVs needed) ----------
// Filament lit materials read normals from the TANGENTS attribute as a
// quaternion (n.xyz, 0) — cheap stand-in for a full TBN frame here.
struct MeshData {
  std::vector<float> v;   // interleaved pos(3) + quatnormal(4)
  std::vector<uint16_t> idx;
};
static void push_vert(MeshData& m, float x, float y, float z, float nx, float ny, float nz) {
  m.v.push_back(x);
  m.v.push_back(y);
  m.v.push_back(z);
  m.v.push_back(nx);
  m.v.push_back(ny);
  m.v.push_back(nz);
  m.v.push_back(0.0f);  // quat w — unused for lighting normals
}
static MeshData make_sphere_mesh(float r, int stacks, int slices) {
  MeshData m;
  const float PI = 3.14159265358979f;
  for (int i = 0; i <= stacks; i++) {
    float phi = PI * i / stacks;
    for (int j = 0; j <= slices; j++) {
      float th = 2 * PI * j / slices;
      float nx = std::sin(phi) * std::cos(th), ny = std::sin(phi) * std::sin(th),
            nz = std::cos(phi);
      push_vert(m, r * nx, r * ny, r * nz, nx, ny, nz);
    }
  }
  int stride = slices + 1;
  for (int i = 0; i < stacks; i++)
    for (int j = 0; j < slices; j++) {
      uint16_t a = uint16_t(i * stride + j), b = uint16_t(a + stride);
      uint16_t tri[6] = {a, b, uint16_t(a + 1), uint16_t(a + 1), b, uint16_t(b + 1)};
      m.idx.insert(m.idx.end(), tri, tri + 6);
    }
  return m;
}
static MeshData make_box_mesh(float hx, float hy, float hz) {
  // 24 verts (per-face normals) + 36 indices
  MeshData m;
  const float sx[6] = {1, -1, 0, 0, 0, 0}, sy[6] = {0, 0, 1, -1, 0, 0},
              sz[6] = {0, 0, 0, 0, 1, -1};
  const float c[6][4] = {  // corner sign pairs per face
      {-1, -1, 1, 1}, {1, 1, -1, -1}, {-1, 1, 1, -1},
      {1, -1, -1, 1}, {-1, -1, 1, 1}, {1, 1, -1, -1}};
  for (int f = 0; f < 6; f++) {
    float u[3] = {sy[f] * hx + (sx[f] ? 0 : hy), sy[f] * hx + (sx[f] ? 0 : hy), 0};
    (void)u;
    // pick in-plane axes
    float ax[3], ay[3];
    if (sx[f]) {
      ax[0] = 0; ax[1] = hy; ax[2] = 0;
      ay[0] = 0; ay[1] = 0; ay[2] = hz;
    } else if (sy[f]) {
      ax[0] = hx; ax[1] = 0; ax[2] = 0;
      ay[0] = 0; ay[1] = 0; ay[2] = hz;
    } else {
      ax[0] = hx; ax[1] = 0; ax[2] = 0;
      ay[0] = 0; ay[1] = hy; ay[2] = 0;
    }
    float ctr[3] = {sx[f] * hx, sy[f] * hy, sz[f] * hz};
    const float q[4] = {-1, 1, 1, -1};  // quad corner signs (u, -u+v...)
    const float uu[4] = {-1, 1, 1, -1}, vv[4] = {-1, -1, 1, 1};
    uint16_t base = uint16_t(m.v.size() / 7);
    for (int k = 0; k < 4; k++) {
      push_vert(m, ctr[0] + uu[k] * ax[0] + vv[k] * ay[0],
                ctr[1] + uu[k] * ax[1] + vv[k] * ay[1],
                ctr[2] + uu[k] * ax[2] + vv[k] * ay[2], sx[f], sy[f], sz[f]);
    }
    (void)q;
    uint16_t tri[6] = {base, uint16_t(base + 1), uint16_t(base + 2),
                        base, uint16_t(base + 2), uint16_t(base + 3)};
    m.idx.insert(m.idx.end(), tri, tri + 6);
  }
  return m;
}
struct BodyVis {
  utils::Entity ent;
  TransformManager::Instance tinst;
  VertexBuffer* vb = nullptr;
  IndexBuffer* ib = nullptr;
  MaterialInstance* mi = nullptr;
};

// Viewport helpers (Blender-style grid + split floor halves)
struct FloorHalf {
  utils::Entity ent{};
  VertexBuffer* vb = nullptr;
  IndexBuffer* ib = nullptr;
};
struct GridMesh {
  utils::Entity ent{};
  VertexBuffer* vb = nullptr;
  IndexBuffer* ib = nullptr;
  MaterialInstance* mi = nullptr;
};
static BodyVis make_body_vis(Engine* engine, const MeshData& mesh, Material* mat,
                             float3 color) {
  BodyVis bv;
  bv.ent = engine->getEntityManager().create();
  bv.vb = VertexBuffer::Builder()
              .bufferCount(1)
              .vertexCount(uint32_t(mesh.v.size() / 7))
              .attribute(VertexAttribute::POSITION, 0, VertexBuffer::AttributeType::FLOAT3, 0, 28)
              .attribute(VertexAttribute::TANGENTS, 0, VertexBuffer::AttributeType::FLOAT4, 12, 28)
              .build(*engine);
  bv.vb->setBufferAt(*engine, 0, backend::BufferDescriptor(mesh.v.data(), mesh.v.size() * 4,
                                                           [](void*, size_t, void*) {}));
  bv.ib = IndexBuffer::Builder()
              .indexCount(uint32_t(mesh.idx.size()))
              .bufferType(IndexBuffer::IndexType::USHORT)
              .build(*engine);
  bv.ib->setBuffer(*engine,
                   backend::BufferDescriptor(mesh.idx.data(), mesh.idx.size() * 2,
                                             [](void*, size_t, void*) {}));
  bv.mi = mat->createInstance();
  bv.mi->setParameter("baseColor", color);
  bv.mi->setParameter("roughness", 0.45f);
  RenderableManager::Builder(1)
      .boundingBox({{-1, -1, -1}, {1, 1, 1}})
      .material(0, bv.mi)
      .geometry(0, RenderableManager::PrimitiveType::TRIANGLES, bv.vb, bv.ib, 0,
                uint32_t(mesh.idx.size()))
      .build(*engine, bv.ent);
  auto& tcm = engine->getTransformManager();
  tcm.create(bv.ent);
  bv.tinst = tcm.getInstance(bv.ent);
  return bv;
}

int WINAPI WinMain(HINSTANCE inst, HINSTANCE, LPSTR cmd, int show) {
  // args: <pool.xml> <material.filamat> (rest fixed)
  std::string args(cmd ? cmd : "");
  bool autoshot = args.find("autoshot") != std::string::npos;
  if (autoshot) {
    // proof mode: log to file (GUI apps can't inherit the parent's pipe).
    // Absolute path so it can't silently vanish on a CWD mismatch.
    (void)freopen((std::string(CAUSTICS_ROOT) + "/out/autoshot_stdout.log").c_str(), "w", stdout);
    (void)freopen((std::string(CAUSTICS_ROOT) + "/out/autoshot_stdout.log").c_str(), "w", stderr);
  } else {
    AllocConsole();
    (void)freopen("CONOUT$", "w", stdout);
    (void)freopen("CONOUT$", "w", stderr);
  }
  std::setvbuf(stdout, nullptr, _IONBF, 0);
  std::printf("[start] WinMain args='%s' autoshot=%d\n", args.c_str(), (int)autoshot);
  // strip any surrounding quotes: WinMain's lpCmdLine preserves the raw
  // command line, so a bash-passed "a b c" arrives with literal quotes.
  for (auto& ch : args)
    if (ch == '"') ch = ' ';
  char xml_path[512] = "models/pool.xml", mat_path[512] = "build/materials/caustic_pool.filamat";
  sscanf(args.c_str(), "%511s %511s", xml_path, mat_path);
  std::printf("[start] xml='%s' mat='%s'\n", xml_path, mat_path);
  const int W = 1280, H = 800;

  // ---------- window ----------
  WNDCLASSA wc{};
  wc.lpfnWndProc = wnd_proc;
  wc.hInstance = inst;
  wc.lpszClassName = "CausticsViewer";
  wc.hCursor = LoadCursorA(nullptr, IDC_ARROW);
  RegisterClassA(&wc);
  RECT r{0, 0, W, H};
  AdjustWindowRect(&r, WS_OVERLAPPEDWINDOW, FALSE);
  HWND hwnd = CreateWindowA("CausticsViewer", "Caustics — wave-corrected pool (drag=orbit, wheel=zoom, space=pause, S=shot)",
                            WS_OVERLAPPEDWINDOW, CW_USEDEFAULT, CW_USEDEFAULT,
                            r.right - r.left, r.bottom - r.top, nullptr, nullptr, inst, nullptr);
  ShowWindow(hwnd, show);

  // ---------- MuJoCo ----------
  char err[1024] = {0};
  mjModel* m = mj_loadXML(xml_path, nullptr, err, sizeof(err));
  if (!m) {
    std::printf("[fatal] mj_loadXML('%s') failed: %s\n", xml_path, err);
    if (!autoshot) MessageBoxA(nullptr, err, "mj_loadXML failed", MB_OK | MB_ICONERROR);
    return 1;
  }
  std::printf("[ok] mujoco loaded (%d bodies)\n", m->nbody);
  mjData* d = mj_makeData(m);
  int id_sphere = mj_name2id(m, mjOBJ_BODY, "float_sphere");
  int id_hull = mj_name2id(m, mjOBJ_BODY, "hull");
  twomed::Env env;

  // ---------- Filament ----------
  Engine* engine = Engine::create(Engine::Backend::OPENGL);
  SwapChain* swapChain = engine->createSwapChain((void*)hwnd, SwapChain::CONFIG_SRGB_COLORSPACE);
  Renderer* renderer = engine->createRenderer();
  Scene* scene = engine->createScene();
  View* view = engine->createView();
  view->setScene(scene);
  view->setPostProcessingEnabled(false);

  auto& em = engine->getEntityManager();
  Camera* camera = engine->createCamera(em.create());
  camera->setProjection(40.0, double(W) / double(H), 0.1, 100.0, Camera::Fov::VERTICAL);
  view->setCamera(camera);
  view->setViewport({0, 0, (uint32_t)W, (uint32_t)H});

  // ---------- caustic maps: wave-corrected and raw geometric quadrature ----------
  // 1024^2 because the Airy band needs >= 3 px per fringe width (EVIDENCE.md §1)
  const int TW = 1024, TH = 1024;
  caust::WaterParams wp;
  auto bake_rgba = [&](float t, bool wave, float* peak_out) {
    std::vector<uint8_t> rgba((size_t)TW * TH * 4);
    float peak = 0.0f;
    if (wave) {
      auto field = caust::bake(TW, TH, t, wp, false, 0.02f);
      for (size_t i = 0; i < field.size(); i++) peak = std::max(peak, field[i]);
      auto srgb = caust::tonemap(field);
      for (int i = 0; i < TW * TH; i++) {
        rgba[i * 4 + 0] = srgb[i * 3 + 0];
        rgba[i * 4 + 1] = srgb[i * 3 + 1];
        rgba[i * 4 + 2] = srgb[i * 3 + 2];
        rgba[i * 4 + 3] = 255;
      }
    } else {
      auto g = caust::bake(TW, TH, t, wp, true, 0.02f);  // single channel
      for (size_t i = 0; i < g.size(); i++) peak = std::max(peak, g[i]);
      std::vector<float> rgb(g.size() * 3);
      for (size_t i = 0; i < g.size(); i++) {
        rgb[i * 3 + 0] = rgb[i * 3 + 1] = rgb[i * 3 + 2] = g[i];
      }
      auto srgb = caust::tonemap(rgb);
      for (int i = 0; i < TW * TH; i++) {
        rgba[i * 4 + 0] = srgb[i * 3 + 0];
        rgba[i * 4 + 1] = srgb[i * 3 + 1];
        rgba[i * 4 + 2] = srgb[i * 3 + 2];
        rgba[i * 4 + 3] = 255;
      }
    }
    if (peak_out) *peak_out = peak;
    return rgba;
  };
  auto upload = [&](Texture* tex, const std::vector<uint8_t>& rgba) {
    uint8_t* owned = new uint8_t[rgba.size()];
    std::memcpy(owned, rgba.data(), rgba.size());
    Texture::PixelBufferDescriptor pb(owned, rgba.size(), backend::PixelDataFormat::RGBA,
                                      backend::PixelDataType::UBYTE,
                                      [](void* b, size_t, void*) { delete[] (uint8_t*)b; });
    tex->setImage(*engine, 0, std::move(pb));
    tex->generateMipmaps(*engine);
  };
  auto make_tex = [&]() {
    return Texture::Builder().width(TW).height(TH).levels(0xFF).sampler(Texture::Sampler::SAMPLER_2D)
        .format(Texture::InternalFormat::RGBA8)
        .usage(Texture::Usage::DEFAULT | Texture::Usage::GEN_MIPMAPPABLE)
        .build(*engine);
  };
  Texture* causticTex = make_tex();     // wave-corrected
  Texture* causticTexGeo = make_tex();  // raw geometric quadrature
  upload(causticTex, bake_rgba(1.7f, true, &g_app.peak_wave));
  upload(causticTexGeo, bake_rgba(1.7f, false, &g_app.peak_geo));

  auto mat_blob = read_file(mat_path);
  Material* mat = Material::Builder().package(mat_blob.data(), mat_blob.size()).build(*engine);
  MaterialInstance* mi = mat->createInstance();     // wave-corrected
  MaterialInstance* miGeo = mat->createInstance();  // geometric
  TextureSampler sampler(TextureSampler::MinFilter::LINEAR_MIPMAP_LINEAR,
                         TextureSampler::MagFilter::LINEAR);
  sampler.setWrapModeS(TextureSampler::WrapMode::REPEAT);
  sampler.setWrapModeT(TextureSampler::WrapMode::REPEAT);
  sampler.setAnisotropy(8.0f);  // moiré reduction on the oblique floor
  mi->setParameter("causticMap", causticTex, sampler);
  mi->setParameter("intensity", 1.0f);
  miGeo->setParameter("causticMap", causticTexGeo, sampler);
  miGeo->setParameter("intensity", 1.0f);

  struct V { float p[3]; float uv[2]; };
  // One quad builder -> two floor halves, so the A/B comparison sits side by side
  // in a single scene (Blender-style split, not two windows).
  auto make_quad = [&](float x0, float x1, MaterialInstance* m) {
    V q[4] = {{{x0, -3, -1}, {0, 0}},
              {{x1, -3, -1}, {1, 0}},
              {{x1, 3, -1}, {1, 1}},
              {{x0, 3, -1}, {0, 1}}};
    uint16_t qi[6] = {0, 1, 2, 0, 2, 3};
    VertexBuffer* v = VertexBuffer::Builder()
                          .bufferCount(1)
                          .vertexCount(4)
                          .attribute(VertexAttribute::POSITION, 0,
                                     VertexBuffer::AttributeType::FLOAT3, 0, 20)
                          .attribute(VertexAttribute::UV0, 0,
                                     VertexBuffer::AttributeType::FLOAT2, 12, 20)
                          .build(*engine);
    v->setBufferAt(*engine, 0,
                   backend::BufferDescriptor(q, sizeof(q), [](void*, size_t, void*) {}));
    IndexBuffer* i2 = IndexBuffer::Builder().indexCount(6)
                          .bufferType(IndexBuffer::IndexType::USHORT)
                          .build(*engine);
    i2->setBuffer(*engine,
                  backend::BufferDescriptor(qi, sizeof(qi), [](void*, size_t, void*) {}));
    FloorHalf fh;
    fh.vb = v;
    fh.ib = i2;
    fh.ent = em.create();
    RenderableManager::Builder(1)
        .boundingBox({{x0, -3, -1}, {x1, 3, -1}})
        .material(0, m)
        .geometry(0, RenderableManager::PrimitiveType::TRIANGLES, v, i2, 0, 6)
        .culling(false)
        .build(*engine, fh.ent);
    scene->addEntity(fh.ent);
    return fh;
  };
  FloorHalf leftFloor = make_quad(-4.0f, 0.0f, miGeo);
  FloorHalf rightFloor = make_quad(0.0f, 4.0f, mi);

  // ---------- Blender-style viewport grid (toggle with G) ----------
  auto gridblob = read_file((std::string(CAUSTICS_ROOT) + "/build/materials/grid_lines.filamat").c_str());
  Material* gridMat = Material::Builder().package(gridblob.data(), gridblob.size()).build(*engine);
  auto make_lines = [&](const std::vector<float>& segs, float3 tint, float alpha) {
    uint32_t nv = uint32_t(segs.size() / 3);
    std::vector<uint16_t> idx(nv);
    for (uint32_t i = 0; i < nv; i++) idx[i] = uint16_t(i);
    VertexBuffer* v = VertexBuffer::Builder()
                          .bufferCount(1)
                          .vertexCount(nv)
                          .attribute(VertexAttribute::POSITION, 0,
                                     VertexBuffer::AttributeType::FLOAT3, 0, 12)
                          .build(*engine);
    float* pcopy = new float[segs.size()];
    std::memcpy(pcopy, segs.data(), segs.size() * sizeof(float));
    v->setBufferAt(*engine, 0,
                   backend::BufferDescriptor(pcopy, segs.size() * sizeof(float),
                                             [](void* b, size_t, void*) { delete[] (float*)b; }));
    IndexBuffer* i2 = IndexBuffer::Builder().indexCount(nv)
                          .bufferType(IndexBuffer::IndexType::USHORT)
                          .build(*engine);
    uint16_t* icopy = new uint16_t[idx.size()];
    std::memcpy(icopy, idx.data(), idx.size() * sizeof(uint16_t));
    i2->setBuffer(*engine,
                  backend::BufferDescriptor(icopy, idx.size() * sizeof(uint16_t),
                                            [](void* b, size_t, void*) { delete[] (uint16_t*)b; }));
    GridMesh gm;
    gm.vb = v;
    gm.ib = i2;
    gm.mi = gridMat->createInstance();
    gm.mi->setParameter("tint", tint);
    gm.mi->setParameter("alpha", alpha);
    gm.ent = em.create();
    RenderableManager::Builder(1)
        .boundingBox({{-5, -5, -1.2f}, {5, 5, -0.8f}})
        .material(0, gm.mi)
        .geometry(0, RenderableManager::PrimitiveType::LINES, v, i2, 0, nv)
        .culling(false)
        .priority(2)
        .build(*engine, gm.ent);
    scene->addEntity(gm.ent);
    return gm;
  };
  const float gz = -0.995f;  // a hair above the pool floor: no z-fighting
  std::vector<float> minorSegs, majorSegs;
  for (int i = -10; i <= 10; i++) {
    float c = i * 0.5f;
    if (i % 4 != 0 && i != 0) {
      minorSegs.insert(minorSegs.end(), {-5.0f, c, gz, 5.0f, c, gz});
      minorSegs.insert(minorSegs.end(), {c, -5.0f, gz, c, 5.0f, gz});
    } else if (i != 0) {
      majorSegs.insert(majorSegs.end(), {-5.0f, c, gz, 5.0f, c, gz});
      majorSegs.insert(majorSegs.end(), {c, -5.0f, gz, c, 5.0f, gz});
    }
  }
  std::vector<float> xAxis = {-5.0f, 0.0f, gz, 5.0f, 0.0f, gz};
  std::vector<float> yAxis = {0.0f, -5.0f, gz, 0.0f, 5.0f, gz};
  GridMesh gMinor = make_lines(minorSegs, float3{0.30f, 0.30f, 0.33f}, 0.35f);
  GridMesh gMajor = make_lines(majorSegs, float3{0.48f, 0.48f, 0.52f}, 0.60f);
  GridMesh gAxisX = make_lines(xAxis, float3{0.85f, 0.22f, 0.22f}, 0.95f);
  GridMesh gAxisY = make_lines(yAxis, float3{0.30f, 0.80f, 0.32f}, 0.95f);

  // ---------- water surface at z=0 (transparent, animated ripples) ----------
  auto wblob = read_file((std::string(CAUSTICS_ROOT) + "/build/materials/water_surface.filamat").c_str());
  Material* waterMat = Material::Builder().package(wblob.data(), wblob.size()).build(*engine);
  MaterialInstance* waterMi = waterMat->createInstance();
  waterMi->setParameter("tint", float3{0.10f, 0.38f, 0.52f});
  waterMi->setParameter("time", 0.0f);
  V wquad[4] = {{{-3, -3, 0}, {0, 0}}, {{3, -3, 0}, {1, 0}},
                {{3, 3, 0}, {1, 1}},   {{-3, 3, 0}, {0, 1}}};
  VertexBuffer* wvb = VertexBuffer::Builder()
                          .bufferCount(1)
                          .vertexCount(4)
                          .attribute(VertexAttribute::POSITION, 0, VertexBuffer::AttributeType::FLOAT3,
                                     0, 20)
                          .attribute(VertexAttribute::UV0, 0, VertexBuffer::AttributeType::FLOAT2, 12,
                                     20)
                          .build(*engine);
  wvb->setBufferAt(*engine, 0, backend::BufferDescriptor(wquad, sizeof(wquad),
                                                         [](void*, size_t, void*) {}));
  uint16_t wqi[6] = {0, 1, 2, 0, 2, 3};
  IndexBuffer* wib = IndexBuffer::Builder().indexCount(6).bufferType(IndexBuffer::IndexType::USHORT)
                         .build(*engine);
  wib->setBuffer(*engine,
                 backend::BufferDescriptor(wqi, sizeof(wqi), [](void*, size_t, void*) {}));
  utils::Entity waterE = em.create();
  RenderableManager::Builder(1)
      .boundingBox({{-3, -3, 0}, {3, 3, 0}})
      .material(0, waterMi)
      .geometry(0, RenderableManager::PrimitiveType::TRIANGLES, wvb, wib, 0, 6)
      .culling(false)
      .build(*engine, waterE);
  scene->addEntity(waterE);

  // ---------- directional light (lit materials need one) ----------
  utils::Entity lightE = em.create();
  LightManager::Builder(LightManager::Type::DIRECTIONAL)
      .color({1.0f, 0.96f, 0.88f})
      .intensity(60000.0f)
      .direction(normalize(float3{-0.45f, -0.35f, -1.0f}))
      .castShadows(true)
      .build(*engine, lightE);
  scene->addEntity(lightE);
  camera->setExposure(1.4f);  // lift bodies out of the dark

  // ---------- floating bodies (sphere + hull box) ----------
  auto mat_blob2 = read_file((std::string(CAUSTICS_ROOT) + "/build/materials/body_lit.filamat").c_str());
  Material* bodyMat =
      Material::Builder().package(mat_blob2.data(), mat_blob2.size()).build(*engine);
  MeshData sphereMesh = make_sphere_mesh(0.15f, 20, 28);
  MeshData hullMesh = make_box_mesh(0.25f, 0.18f, 0.15f);
  BodyVis sphereVis = make_body_vis(engine, sphereMesh, bodyMat, float3{0.85f, 0.55f, 0.25f});
  BodyVis hullVis = make_body_vis(engine, hullMesh, bodyMat, float3{0.75f, 0.28f, 0.20f});
  scene->addEntity(sphereVis.ent);
  scene->addEntity(hullVis.ent);
  auto& tcm = engine->getTransformManager();

  double sphere_p[3] = {0.15, 0, 0};
  double hullbox_p[3] = {0.25, 0.18, 0.15};
  LARGE_INTEGER freq, t0;
  QueryPerformanceFrequency(&freq);
  QueryPerformanceCounter(&t0);
  double acc = 0, last = 0;
  int shot_n = 0;
  int shot_at = 90;     // autoshot: frame of the next capture
  int shots_taken = 0;  // autoshot: 3-shot A/B/A proof (water on / off / red)
  if (autoshot) {
    // canonical front view so the A/B split maps cleanly onto screen halves:
    // screen-left = world +X = wave half, screen-right = world -X = geometric half
    g_app.yaw = 0.0f;
    g_app.pitch = 0.42f;
  }

  // ---------- main loop ----------
  MSG msg{};
  while (!g_app.quit) {
    while (PeekMessageA(&msg, nullptr, 0, 0, PM_REMOVE)) {
      if (msg.message == WM_QUIT) g_app.quit = true;
      TranslateMessage(&msg);
      DispatchMessageA(&msg);
    }
    if (g_app.quit) break;

    LARGE_INTEGER now;
    QueryPerformanceCounter(&now);
    double t = double(now.QuadPart - t0.QuadPart) / double(freq.QuadPart);
    double dt_real = std::min(t - last, 0.1);
    last = t;

    // physics: fixed 2ms substeps with our buoyancy
    if (!g_app.paused) {
      acc += dt_real;
      double dt = m->opt.timestep;
      int n = 0;
      while (acc >= dt && n < 50) {
        mj_forward(m, d);
        if (id_sphere >= 0) {
          auto b = body_from_mj(d, id_sphere, twomed::Shape::Sphere, sphere_p, 14.137167);
          auto w = twomed::archimedes(b, env);
          d->xfrc_applied[id_sphere * 6 + 2] = w.F[2];
        }
        if (id_hull >= 0) {
          auto b = body_from_mj(d, id_hull, twomed::Shape::Box, hullbox_p, 28.0);
          auto w = twomed::archimedes(b, env);
          d->xfrc_applied[id_hull * 6 + 0] = w.F[0];
          d->xfrc_applied[id_hull * 6 + 1] = w.F[1];
          d->xfrc_applied[id_hull * 6 + 2] = w.F[2];
          d->xfrc_applied[id_hull * 6 + 3] = w.T[0];
          d->xfrc_applied[id_hull * 6 + 4] = w.T[1];
          d->xfrc_applied[id_hull * 6 + 5] = w.T[2];
        }
        mj_step(m, d);
        acc -= dt;
        n++;
        g_app.sim_time += (float)dt;
      }
      // pose sync: MuJoCo bodies -> Filament transforms (after stepping)
      auto sync_body = [&](int bid, BodyVis& bv) {
        if (bid < 0) return;
        mjtNum R9[9];
        mju_quat2Mat(R9, d->xquat + bid * 4);
        // mat4: rotation columns = rows of R (mju_quat2Mat is row-major), translation
        float4 c0{(float)R9[0], (float)R9[3], (float)R9[6], 0};
        float4 c1{(float)R9[1], (float)R9[4], (float)R9[7], 0};
        float4 c2{(float)R9[2], (float)R9[5], (float)R9[8], 0};
        float4 c3{(float)d->xpos[bid * 3], (float)d->xpos[bid * 3 + 1],
                  (float)d->xpos[bid * 3 + 2], 1};
        tcm.setTransform(bv.tinst, mat4f{c0, c1, c2, c3});
      };
      sync_body(id_sphere, sphereVis);
      sync_body(id_hull, hullVis);
      // animated caustics: re-bake every 20 frames (~3 Hz water)
      if ((g_app.frame % 20) == 0) {
        float bt = 1.7f + g_app.sim_time * 0.9f;
        bool need_wave = g_app.split || g_app.use_wave;
        bool need_geo = g_app.split || !g_app.use_wave;
        auto t0 = std::chrono::steady_clock::now();
        if (need_wave) upload(causticTex, bake_rgba(bt, true, &g_app.peak_wave));
        auto t1 = std::chrono::steady_clock::now();
        if (need_geo) upload(causticTexGeo, bake_rgba(bt, false, &g_app.peak_geo));
        auto t2 = std::chrono::steady_clock::now();
        g_app.bake_ms = std::chrono::duration<double, std::milli>(t1 - t0).count();
        g_app.bake_geo_ms = std::chrono::duration<double, std::milli>(t2 - t1).count();
      }
    }

    // ---- viewport state: grid visibility + shading mode (Blender-ish keys) ----
    static bool last_grid = true, last_wave = true, last_split = true;
    if (last_grid != g_app.show_grid) {
      GridMesh* meshes[4] = {&gMinor, &gMajor, &gAxisX, &gAxisY};
      for (GridMesh* g : meshes) {
        if (g_app.show_grid) {
          scene->addEntity(g->ent);
        } else {
          scene->remove(g->ent);
        }
      }
      last_grid = g_app.show_grid;
    }
    if (last_wave != g_app.use_wave || last_split != g_app.split) {
      auto& rm2 = engine->getRenderableManager();
      MaterialInstance* active = g_app.use_wave ? mi : miGeo;
      rm2.setMaterialInstanceAt(rm2.getInstance(leftFloor.ent), 0,
                                g_app.split ? miGeo : active);
      rm2.setMaterialInstanceAt(rm2.getInstance(rightFloor.ent), 0,
                                g_app.split ? mi : active);
      last_wave = g_app.use_wave;
      last_split = g_app.split;
    }

    // water shimmer animates on wall-clock time, so it moves even when paused
    waterMi->setParameter("time", (float)t);

    // orbit camera around the (pannable) target
    float3 target{g_app.tx, g_app.ty, g_app.tz};
    camera->lookAt(target + cam_eye(), target);

    // Blender-style header: live viewport stats in the title bar
    if ((g_app.frame % 30) == 0) {
      char title[320];
      snprintf(title, sizeof(title),
               "caustics viewport  |  %s  |  %s  |  %dx%d  |  bake: wave %.1f ms, geo "
               "%.1f ms  |  peak: geo %.2fx, wave %.2fx  |  %s",
               g_app.split ? "A/B split (left = geometric, right = wave-corrected)"
                           : (g_app.use_wave ? "wave-corrected" : "raw geometric"),
               g_app.paused ? "PAUSED" : "live", TW, TH, g_app.bake_ms, g_app.bake_geo_ms,
               g_app.peak_geo, g_app.peak_wave, g_app.show_grid ? "grid on" : "grid off");
      SetWindowTextA(hwnd, title);
    }

    if (renderer->beginFrame(swapChain)) {
      renderer->render(view);
      if (g_app.want_shot || (autoshot && shots_taken < 3 && g_app.frame >= shot_at)) {
        g_app.want_shot = false;
        std::vector<uint8_t> px((size_t)W * H * 3);
        backend::PixelBufferDescriptor pb(px.data(), px.size(), backend::PixelDataFormat::RGB,
                                          backend::PixelDataType::UBYTE, 1, 0, 0, 0,
                                          [](void*, size_t, void*) {});
        renderer->readPixels(0, 0, W, H, std::move(pb));
        renderer->endFrame();
        engine->flushAndWait();
        std::vector<uint8_t> top((size_t)W * H * 3);
        for (int y = 0; y < H; y++)
          std::memcpy(top.data() + (size_t)y * W * 3,
                      px.data() + (size_t)(H - 1 - y) * W * 3, (size_t)W * 3);
        char name[64];
        snprintf(name, sizeof(name), "out/shot_%02d.png", shot_n++);
        if (write_png(name, W, H, top)) std::printf("wrote %s\n", name);
        if (autoshot) {
          double sum = 0;
          for (size_t i = 0; i < px.size(); i++) sum += px[i];
          auto& rm = engine->getRenderableManager();
          std::printf("[diag] shot=%d renderables=%zu lights=%zu waterHasRenderable=%d sens=%.1f "
                      "meanpx=%.2f\n",
                      shots_taken, scene->getRenderableCount(), scene->getLightCount(),
                      (int)rm.hasComponent(waterE), camera->getSensitivity(),
                      sum / (double)px.size());
          std::fflush(stdout);
          shots_taken++;
          if (shots_taken == 1) {  // A: water visible
            scene->remove(waterE);
            shot_at = 120;
          } else if (shots_taken == 2) {  // B: water removed -> reference
            scene->addEntity(waterE);
            waterMi->setParameter("tint", float3{1.0f, 0.0f, 0.0f});
            shot_at = 150;
          } else {  // C: red water proves the material actually draws
            g_app.quit = true;
          }
        }
        g_app.frame++;
        continue;
      }
      renderer->endFrame();
    }
    g_app.frame++;
  }

  engine->destroy(leftFloor.ent);
  engine->destroy(leftFloor.vb);
  engine->destroy(leftFloor.ib);
  engine->destroy(rightFloor.ent);
  engine->destroy(rightFloor.vb);
  engine->destroy(rightFloor.ib);
  engine->destroy(causticTex);
  engine->destroy(causticTexGeo);
  engine->destroy(mi);
  engine->destroy(miGeo);
  engine->destroy(mat);
  {
    GridMesh* gmeshes[4] = {&gMinor, &gMajor, &gAxisX, &gAxisY};
    for (GridMesh* g : gmeshes) {
      engine->destroy(g->ent);
      engine->destroy(g->mi);
      engine->destroy(g->vb);
      engine->destroy(g->ib);
    }
  }
  engine->destroy(gridMat);
  // body vis: renderable (ent) first, then its material instance, then buffers
  engine->destroy(sphereVis.ent);
  engine->destroy(sphereVis.mi);
  engine->destroy(sphereVis.vb);
  engine->destroy(sphereVis.ib);
  engine->destroy(hullVis.ent);
  engine->destroy(hullVis.mi);
  engine->destroy(hullVis.vb);
  engine->destroy(hullVis.ib);
  engine->destroy(bodyMat);
  engine->destroy(lightE);
  engine->destroy(waterE);
  engine->destroy(waterMi);
  engine->destroy(wvb);
  engine->destroy(wib);
  engine->destroy(waterMat);
  engine->destroyCameraComponent(camera->getEntity());
  em.destroy(camera->getEntity());
  engine->destroy(view);
  engine->destroy(scene);
  engine->destroy(renderer);
  engine->destroy(swapChain);
  Engine::destroy(&engine);
  mj_deleteData(d);
  mj_deleteModel(m);
  DestroyWindow(hwnd);
  return 0;
}
