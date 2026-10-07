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
  bool dragging = false;
  int last_x = 0, last_y = 0;
  float sim_time = 0;
  int frame = 0;
};
static App g_app;

static LRESULT CALLBACK wnd_proc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
  switch (msg) {
    case WM_DESTROY:
      g_app.quit = true;
      return 0;
    case WM_KEYDOWN:
      if (wp == VK_ESCAPE) g_app.quit = true;
      if (wp == VK_SPACE) g_app.paused = !g_app.paused;
      if (wp == 'S') g_app.want_shot = true;
      return 0;
    case WM_LBUTTONDOWN:
      g_app.dragging = true;
      g_app.last_x = LOWORD(lp);
      g_app.last_y = HIWORD(lp);
      SetCapture(hwnd);
      return 0;
    case WM_LBUTTONUP:
      g_app.dragging = false;
      ReleaseCapture();
      return 0;
    case WM_MOUSEMOVE:
      if (g_app.dragging) {
        int x = LOWORD(lp), y = HIWORD(lp);
        g_app.yaw += (x - g_app.last_x) * 0.005f;
        g_app.pitch = std::clamp(g_app.pitch + (y - g_app.last_y) * 0.005f, 0.15f, 1.45f);
        g_app.last_x = x;
        g_app.last_y = y;
      }
      return 0;
    case WM_MOUSEWHEEL:
      g_app.dist = std::clamp(g_app.dist - GET_WHEEL_DELTA_WPARAM(wp) * 0.002f, 3.0f, 25.0f);
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
    (void)freopen("D:/ValueProjects/caustics/out/autoshot_stdout.log", "w", stdout);
    (void)freopen("D:/ValueProjects/caustics/out/autoshot_stdout.log", "w", stderr);
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

  // caustic texture (512 + mipmaps; re-baked live every 15 frames)
  const int TW = 512, TH = 512;
  caust::WaterParams wp;
  auto bake_rgba = [&](float t) {
    auto field = caust::bake(TW, TH, t, wp, false, 0.02f);
    auto srgb = caust::tonemap(field);
    std::vector<uint8_t> rgba((size_t)TW * TH * 4);
    for (int i = 0; i < TW * TH; i++) {
      rgba[i * 4 + 0] = srgb[i * 3 + 0];
      rgba[i * 4 + 1] = srgb[i * 3 + 1];
      rgba[i * 4 + 2] = srgb[i * 3 + 2];
      rgba[i * 4 + 3] = 255;
    }
    return rgba;
  };
  std::vector<uint8_t> rgba0 = bake_rgba(1.7f);
  Texture* causticTex =
      Texture::Builder().width(TW).height(TH).levels(0xFF).sampler(Texture::Sampler::SAMPLER_2D)
          .format(Texture::InternalFormat::RGBA8)
          .usage(Texture::Usage::DEFAULT | Texture::Usage::GEN_MIPMAPPABLE)
          .build(*engine);
  {
    uint8_t* owned = new uint8_t[rgba0.size()];
    std::memcpy(owned, rgba0.data(), rgba0.size());
    Texture::PixelBufferDescriptor pb(owned, rgba0.size(), backend::PixelDataFormat::RGBA,
                                      backend::PixelDataType::UBYTE,
                                      [](void* b, size_t, void*) { delete[] (uint8_t*)b; });
    causticTex->setImage(*engine, 0, std::move(pb));
    causticTex->generateMipmaps(*engine);
  }

  auto mat_blob = read_file(mat_path);
  Material* mat = Material::Builder().package(mat_blob.data(), mat_blob.size()).build(*engine);
  MaterialInstance* mi = mat->createInstance();
  TextureSampler sampler(TextureSampler::MinFilter::LINEAR_MIPMAP_LINEAR,
                         TextureSampler::MagFilter::LINEAR);
  sampler.setWrapModeS(TextureSampler::WrapMode::REPEAT);
  sampler.setWrapModeT(TextureSampler::WrapMode::REPEAT);
  sampler.setAnisotropy(8.0f);  // moiré reduction on the oblique floor
  mi->setParameter("causticMap", causticTex, sampler);
  mi->setParameter("intensity", 1.0f);

  struct V { float p[3]; float uv[2]; };
  V quad[4] = {{{-3, -3, -1}, {0, 0}}, {{3, -3, -1}, {1, 0}},
               {{3, 3, -1}, {1, 1}},   {{-3, 3, -1}, {0, 1}}};
  uint16_t qi[6] = {0, 1, 2, 0, 2, 3};
  VertexBuffer* vb = VertexBuffer::Builder()
                         .bufferCount(1)
                         .vertexCount(4)
                         .attribute(VertexAttribute::POSITION, 0, VertexBuffer::AttributeType::FLOAT3,
                                    0, 20)
                         .attribute(VertexAttribute::UV0, 0, VertexBuffer::AttributeType::FLOAT2, 12,
                                    20)
                         .build(*engine);
  vb->setBufferAt(*engine, 0, backend::BufferDescriptor(quad, sizeof(quad),
                                                        [](void*, size_t, void*) {}));
  IndexBuffer* ib = IndexBuffer::Builder().indexCount(6).bufferType(IndexBuffer::IndexType::USHORT)
                        .build(*engine);
  ib->setBuffer(*engine,
                backend::BufferDescriptor(qi, sizeof(qi), [](void*, size_t, void*) {}));
  utils::Entity floorE = em.create();
  RenderableManager::Builder(1)
      .boundingBox({{-3, -3, -1}, {3, 3, -1}})
      .material(0, mi)
      .geometry(0, RenderableManager::PrimitiveType::TRIANGLES, vb, ib, 0, 6)
      .culling(false)
      .build(*engine, floorE);
  scene->addEntity(floorE);

  // ---------- water surface at z=0 (transparent, animated ripples) ----------
  auto wblob = read_file("D:/ValueProjects/caustics/build/materials/water_surface.filamat");
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
  IndexBuffer* wib = IndexBuffer::Builder().indexCount(6).bufferType(IndexBuffer::IndexType::USHORT)
                         .build(*engine);
  wib->setBuffer(*engine,
                 backend::BufferDescriptor(qi, sizeof(qi), [](void*, size_t, void*) {}));
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
  auto mat_blob2 = read_file("D:/ValueProjects/caustics/build/materials/body_lit.filamat");
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
      // animated caustics: re-bake every 15 frames (~4 Hz water)
      if ((g_app.frame % 15) == 0) {
        auto rgba = bake_rgba(1.7f + g_app.sim_time * 0.9f);
        uint8_t* owned = new uint8_t[rgba.size()];
        std::memcpy(owned, rgba.data(), rgba.size());
        Texture::PixelBufferDescriptor pb(owned, rgba.size(), backend::PixelDataFormat::RGBA,
                                          backend::PixelDataType::UBYTE,
                                          [](void* b, size_t, void*) { delete[] (uint8_t*)b; });
        causticTex->setImage(*engine, 0, std::move(pb));
        causticTex->generateMipmaps(*engine);
      }
    }

    // water shimmer animates on wall-clock time, so it moves even when paused
    waterMi->setParameter("time", (float)t);

    // orbit camera
    float3 eye{std::sin(g_app.yaw) * std::cos(g_app.pitch) * g_app.dist,
               std::cos(g_app.yaw) * std::cos(g_app.pitch) * g_app.dist,
               std::sin(g_app.pitch) * g_app.dist};
    camera->lookAt(eye, float3{0, 0, -0.5});

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

  engine->destroy(floorE);
  engine->destroy(vb);
  engine->destroy(ib);
  engine->destroy(causticTex);
  engine->destroy(mi);
  engine->destroy(mat);
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
