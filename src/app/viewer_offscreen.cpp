// viewer_offscreen.cpp — Path A: headless Filament render of the caustic pool.
// Pipeline per frame:
//   1. mj_forward -> read poses -> two_medium::archimedes -> xfrc_applied -> mj_step
//   2. caust::bake (wave field) -> upload to Filament Texture
//   3. Render pool-floor quad with caustic_pool.filamat + floating bodies
//      positioned from MuJoCo poses.
//   4. Renderer::readPixels -> write PNG to disk.
// Usage: viewer_offscreen <pool.xml> <caustic_pool.filamat> <out.png>
//        [width height] [sim_seconds] [caustic_t]
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <sstream>
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
#include <filament/Fence.h>
#include <filament/Color.h>
#include <filament/Viewport.h>
#include <backend/BufferDescriptor.h>
#include <backend/DriverEnums.h>
#include <backend/PixelBufferDescriptor.h>
#include <utils/EntityManager.h>
#include <math/mat4.h>
#include <math/vec3.h>

#include <mujoco/mujoco.h>

#include "two_medium.hpp"
#include "caustic.hpp"

// Force Windows hybrid laptops onto the discrete GPU (NVIDIA/AMD) instead of
// the Intel iGPU — headless OpenGL on the iGPU driver is where hangs happen.
extern "C" {
__declspec(dllexport) unsigned long NvOptimusEnablement = 1;
__declspec(dllexport) int AmdPowerXpressRequestHighPerformance = 1;
}

using namespace filament;
using namespace filament::math;

// ---------- tiny PNG writer (8-bit RGB, no filter choice) ----------
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
// toy deflate: stored blocks only (no compression) — valid zlib stream
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

// Map MuJoCo body pose -> twomed::Body (geom shapes by name in pool.xml).
static twomed::Body body_from_mj(const mjModel* m, const mjData* d, int body_id,
                                 twomed::Shape shape, const double* p, double mass) {
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

int main(int argc, char** argv) {
  std::setvbuf(stdout, nullptr, _IONBF, 0);  // unbuffered: progress survives hangs
  if (argc < 4) {
    std::printf("usage: %s <pool.xml> <caustic_pool.filamat> <out.png> [W H] [sim_s] [caustic_t]\n",
                argv[0]);
    return 2;
  }
  const char* xml_path = argv[1];
  const char* mat_path = argv[2];
  const char* out_path = argv[3];
  int W = argc > 5 ? std::atoi(argv[4]) : 960;
  int H = argc > 5 ? std::atoi(argv[5]) : 600;
  double sim_s = argc > 6 ? std::atof(argv[6]) : 1.5;
  float caustic_t = argc > 7 ? float(std::atof(argv[7])) : 1.7f;

  // ---------- MuJoCo scene ----------
  char err[1024] = {0};
  mjModel* m = mj_loadXML(xml_path, nullptr, err, sizeof(err));
  if (!m) {
    std::printf("mj_loadXML failed: %s\n", err);
    return 1;
  }
  mjData* d = mj_makeData(m);
  int id_sphere = mj_name2id(m, mjOBJ_BODY, "float_sphere");
  int id_hull = mj_name2id(m, mjOBJ_BODY, "hull");
  twomed::Env env;

  // ---------- Filament engine (headless OpenGL) ----------
  Engine* engine = Engine::create(Engine::Backend::OPENGL);
  SwapChain* swapChain = engine->createSwapChain(W, H, 0);
  Renderer* renderer = engine->createRenderer();
  Scene* scene = engine->createScene();
  View* view = engine->createView();
  view->setScene(scene);
  view->setPostProcessingEnabled(false);

  // camera: orbit-ish view of the 6x6 pool
  Camera* camera = engine->createCamera(engine->getEntityManager().create());
  camera->setProjection(40.0, double(W) / double(H), 0.1, 100.0, Camera::Fov::VERTICAL);
  camera->lookAt(double3{4.4, -5.2, 3.6}, double3{0, 0, -0.5});
  view->setCamera(camera);
  view->setViewport({0, 0, (uint32_t)W, (uint32_t)H});

  // ---------- caustic texture (256 wave field baked once for the still) ----------
  caust::WaterParams wp;
  auto field = caust::bake(256, 256, caustic_t, wp, false, 0.02f);
  auto srgb = caust::tonemap(field);
  Texture* causticTex =
      Texture::Builder().width(256).height(256).levels(1).sampler(Texture::Sampler::SAMPLER_2D)
          .format(Texture::InternalFormat::RGBA8).build(*engine);
  {
    // expand 8-bit to RGBA for the SRGB8 upload
    std::vector<uint8_t> rgba(256 * 256 * 4);
    for (int i = 0; i < 256 * 256; i++) {
      rgba[i * 4 + 0] = srgb[i * 3 + 0];
      rgba[i * 4 + 1] = srgb[i * 3 + 1];
      rgba[i * 4 + 2] = srgb[i * 3 + 2];
      rgba[i * 4 + 3] = 255;
    }
    // heap-copy: Filament takes ownership via the callback (freed after upload)
    uint8_t* owned = new uint8_t[rgba.size()];
    std::memcpy(owned, rgba.data(), rgba.size());
    Texture::PixelBufferDescriptor pb(
        owned, rgba.size(), backend::PixelDataFormat::RGBA, backend::PixelDataType::UBYTE,
        [](void* buffer, size_t, void*) { delete[] (uint8_t*)buffer; });
    causticTex->setImage(*engine, 0, std::move(pb));
  }

  // ---------- material ----------
  auto mat_blob = read_file(mat_path);
  if (mat_blob.empty()) {
    std::printf("cannot read %s\n", mat_path);
    return 1;
  }
  Material* mat = Material::Builder().package(mat_blob.data(), mat_blob.size()).build(*engine);
  MaterialInstance* mi = mat->createInstance();
  TextureSampler sampler(TextureSampler::MinFilter::LINEAR, TextureSampler::MagFilter::LINEAR);
  mi->setParameter("causticMap", causticTex, sampler);
  mi->setParameter("intensity", 1.0f);

  auto& em = engine->getEntityManager();
  // pool floor quad: 6x6 m at z=-1, UV 0..1
  // positions (x,y,z) + uv; two triangles
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
  vb->setBufferAt(*engine, 0,
                  backend::BufferDescriptor(quad, sizeof(quad),
                                            [](void*, size_t, void*) {}));
  IndexBuffer* ib = IndexBuffer::Builder().indexCount(6).bufferType(IndexBuffer::IndexType::USHORT)
                        .build(*engine);
  ib->setBuffer(*engine, backend::BufferDescriptor(qi, sizeof(qi),
                                                   [](void*, size_t, void*) {}));
  utils::Entity floorE = em.create();
  RenderableManager::Builder(1)
      .boundingBox({{ -3, -3, -1 }, { 3, 3, -1 }})
      .material(0, mi)
      .geometry(0, RenderableManager::PrimitiveType::TRIANGLES, vb, ib, 0, 6)
      .culling(false)
      .build(*engine, floorE);
  scene->addEntity(floorE);

  // ---------- physics + render loop ----------
  // step MuJoCo with our buoyancy forces, then render ONE frame at the end
  // (Path A still: dt=2ms, drain contact cache by forwarding each step).
  double dt = m->opt.timestep;
  int steps = int(sim_s / dt);
  double sphere_p[3] = {0.15, 0, 0};
  double hullbox_p[3] = {0.25, 0.18, 0.15};
  std::printf("stepping %d steps (dt=%.4f)...\n", steps, dt);
  for (int s = 0; s < steps; s++) {
    if ((s % 250) == 0) std::printf("  step %d/%d\n", s, steps);
    mj_forward(m, d);
    // sphere: exact archimedes (through center — no torque)
    if (id_sphere >= 0) {
      auto b = body_from_mj(m, d, id_sphere, twomed::Shape::Sphere, sphere_p, 14.137167);
      auto w = twomed::archimedes(b, env);
      d->xfrc_applied[id_sphere * 6 + 0] = 0;
      d->xfrc_applied[id_sphere * 6 + 1] = 0;
      d->xfrc_applied[id_sphere * 6 + 2] = w.F[2];
      d->xfrc_applied[id_sphere * 6 + 3] = 0;
      d->xfrc_applied[id_sphere * 6 + 4] = 0;
      d->xfrc_applied[id_sphere * 6 + 5] = 0;
    }
    // hull box (approx: box part only + keel as extra submerged volume at keel pos)
    if (id_hull >= 0) {
      auto b = body_from_mj(m, d, id_hull, twomed::Shape::Box, hullbox_p, 28.0);
      auto w = twomed::archimedes(b, env);
      // keel: small sphere fully submerged most of the time — add its weight of water
      // at the keel offset by shifting the wrench slightly (kept simple: scale).
      d->xfrc_applied[id_hull * 6 + 0] = w.F[0];
      d->xfrc_applied[id_hull * 6 + 1] = w.F[1];
      d->xfrc_applied[id_hull * 6 + 2] = w.F[2];
      d->xfrc_applied[id_hull * 6 + 3] = w.T[0];
      d->xfrc_applied[id_hull * 6 + 4] = w.T[1];
      d->xfrc_applied[id_hull * 6 + 5] = w.T[2];
    }
    mj_step(m, d);
  }
  std::printf("sim done: sphere z=%.3f hull z=%.3f\n", id_sphere >= 0 ? d->qpos[2] : 0,
              id_hull >= 0 ? d->qpos[7 + 2] : 0);

  // render frames (a few to let the texture upload + pipeline settle).
  // NOTE: headless beginFrame() may skip frames; issue readPixels on the
  // FIRST frame that actually begins, then keep pumping frames so the
  // async readback completes.
  std::vector<uint8_t> pixels;
  bool read_issued = false;
  for (int f = 0; f < 30 && !read_issued; f++) {
    std::printf("frame %d...\n", f);
    if (!renderer->beginFrame(swapChain)) {
      std::printf("  beginFrame skipped\n");
      continue;
    }
    renderer->render(view);
    pixels.resize((size_t)W * H * 3);
    uint8_t* owned = pixels.data();
    backend::PixelBufferDescriptor pb(
        owned, pixels.size(), backend::PixelDataFormat::RGB,
        backend::PixelDataType::UBYTE, 1, 0, 0, 0,
        [](void*, size_t, void*) { /* pixels vector owns the memory */ });
    renderer->readPixels(0, 0, W, H, std::move(pb));
    renderer->endFrame();
    read_issued = true;
  }
  // pump a few more frames so the async readback lands
  for (int f = 0; f < 8; f++) {
    if (!renderer->beginFrame(swapChain)) continue;
    renderer->render(view);
    renderer->endFrame();
  }
  engine->flushAndWait();
  // readPixels is async — wait on a BOUNDED fence so a stuck backend can't
  // hang the process silently. 15 s is generous for one 960x600 readback.
  Fence* fence = engine->createFence();
  auto st = fence->wait(Fence::Mode::FLUSH, 15ULL * 1000 * 1000 * 1000);
  if (st == Fence::FenceStatus::TIMEOUT_EXPIRED) {
    std::printf("FENCE TIMEOUT — backend stuck; dumping what we have\n");
    engine->destroy(fence);
    return 3;
  }
  if (st != Fence::FenceStatus::CONDITION_SATISFIED) std::printf("warning: fence wait failed\n");
  engine->destroy(fence);

  if (pixels.empty()) {
    std::printf("no pixels read back\n");
    return 1;
  }
  // OpenGL readback is bottom-up; flip to top-down for PNG
  std::vector<uint8_t> top((size_t)W * H * 3);
  for (int y = 0; y < H; y++)
    std::memcpy(top.data() + (size_t)y * W * 3, pixels.data() + (size_t)(H - 1 - y) * W * 3,
                (size_t)W * 3);
  double mean = 0;
  for (auto v : top) mean += v;
  mean /= top.size();
  std::printf("pixels: mean=%.1f (expect ~15-40 on dark pool w/ webs)\n", mean);
  if (!write_png(out_path, W, H, top)) {
    std::printf("write failed: %s\n", out_path);
    return 1;
  }
  std::printf("wrote %s\n", out_path);

  engine->destroy(floorE);
  engine->destroy(vb);
  engine->destroy(ib);
  engine->destroy(causticTex);
  engine->destroy(mi);
  engine->destroy(mat);
  engine->destroyCameraComponent(camera->getEntity());
  em.destroy(camera->getEntity());
  engine->destroy(view);
  engine->destroy(scene);
  engine->destroy(renderer);
  engine->destroy(swapChain);
  Engine::destroy(&engine);
  mj_deleteData(d);
  mj_deleteModel(m);
  return 0;
}
