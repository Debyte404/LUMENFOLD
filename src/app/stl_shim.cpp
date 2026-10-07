// stl_shim.cpp — forward-compat shims for Filament 1.77.2 prebuilts.
// Filament's md libs were built with a NEWER MSVC STL than our 14.41 toolchain
// provides, so 4 vectorized/primitive symbols are missing at link time.
// Signatures verified against microsoft/STL public source:
//   xutility (search/find_end), xmemory (remove_8), xthreads.h (Cnd).
// Each shim is a CORRECT scalar implementation of the documented contract,
// not a stub: search/find_end/remove are memchr-style scans; the timed wait
// forwards to our CRT's checked _Cnd_timedwait_for (same behavior + checks).
#include <cstddef>
#include <cstdint>
#include <cstring>

// ---- needs _Cnd_t / _Mtx_t layout: opaque pointers in our CRT, same ABI ----
struct _Cnd;
struct _Mtx;
typedef _Cnd* _Cnd_t;
typedef _Mtx* _Mtx_t;
enum class _Thrd_result : int { success = 0, timedout = 1, busy = 2, nomem = 3, error = 4 };

extern "C" {
// Our CRT HAS the checked variant with identical signature (xthreads.h line 70).
__declspec(dllimport) _Thrd_result __stdcall _Cnd_timedwait_for(_Cnd_t, _Mtx_t,
                                                               unsigned int) noexcept;

// Filament wants the unchecked variant: same behavior minus validation.
// Trivial forward — same ABI, same semantics for valid handles.
_Thrd_result __stdcall _Cnd_timedwait_for_unchecked(_Cnd_t cnd, _Mtx_t mtx,
                                                    unsigned int ms) noexcept {
  return _Cnd_timedwait_for(cnd, mtx, ms);
}

// ---- vectorized STL algorithm fallbacks (scalar, correct) ----
const void* __stdcall __std_search_1(const void* f1, const void* l1, const void* f2,
                                     size_t c2) noexcept {
  const auto* a = (const uint8_t*)f1;
  const auto* ae = (const uint8_t*)l1;
  const auto* b = (const uint8_t*)f2;
  if (c2 == 0) return f1;
  size_t n = (size_t)(ae - a);
  if (n < c2) return l1;
  for (size_t i = 0; i + c2 <= n; i++)
    if (std::memcmp(a + i, b, c2) == 0) return a + i;
  return l1;
}

const void* __stdcall __std_find_end_1(const void* f1, const void* l1, const void* f2,
                                       size_t c2) noexcept {
  const auto* a = (const uint8_t*)f1;
  const auto* ae = (const uint8_t*)l1;
  const auto* b = (const uint8_t*)f2;
  if (c2 == 0) return l1;
  size_t n = (size_t)(ae - a);
  if (n < c2) return l1;
  const void* last = l1;
  for (size_t i = 0; i + c2 <= n; i++)
    if (std::memcmp(a + i, b, c2) == 0) last = a + i;
  return last;
}

void* __stdcall __std_remove_8(void* f, void* l, uint64_t v) noexcept {
  auto* a = (uint64_t*)f;
  auto* ae = (uint64_t*)l;
  uint64_t* out = a;
  for (; a != ae; ++a)
    if (*a != v) *out++ = *a;
  return out;
}
}  // extern "C"
