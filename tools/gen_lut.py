import numpy as np
d = np.load('D:/ValueProjects/caustics/src/render/airy_lut.npz')
u, Ai, mx = d['u'], d['Ai'], float(d['mx'])
vals = (Ai / mx).astype(np.float32)
L = []
L.append('// airy_lut.hpp - |Ai(-u)|^2 fold-caustic profile, u in [0,8], 2048 pts.')
L.append('// Generated from scipy.special.airy.')
L.append('#pragma once')
L.append('#include <cstddef>')
L.append('static constexpr std::size_t kAiryN = 2048;')
L.append('static constexpr float kAiryUmax = 8.0f;')
L.append('static constexpr float AIRY_PEAK = %.8ff;' % mx)
L.append('static constexpr float kAiryLUT[kAiryN] = {')
rows = ['  ' + ', '.join('%.7ff' % v for v in vals[i:i + 8]) for i in range(0, len(vals), 8)]
L.append(',\n'.join(rows))
L.append('};')
open('D:/ValueProjects/caustics/src/render/airy_lut.hpp', 'w').write('\n'.join(L) + '\n')
print('header written, peak', mx)
