// SPDX-License-Identifier: AGPL-3.0-only
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <type_traits>
#include <vector>
#ifdef __aarch64__
#include <arm_neon.h>
#endif

struct Half {
    uint16_t bits;
    operator float() const {
#ifdef __aarch64__
        __fp16 value;std::memcpy(&value,&bits,2);return float(value);
#else
        const unsigned e=(bits>>10)&31,m=bits&1023;
        float value=e==31 ? (m?NAN:INFINITY) : std::ldexp(float(e?m+1024:m),e?int(e)-25:-24);
        return bits&32768?-value:value;
#endif
    }
};

struct Workspace {
    std::vector<float> scores;
    std::vector<int> classes;
    std::vector<int64_t> candidates;
};
// Output rows: class, confidence, unrounded x1/y1/x2/y2. No Python callbacks.
template<typename T>
int run(void* handle, const T* scores, const T* boxes, int64_t n,
             double low, double high, double threshold, int64_t topk,
             double left, double top, double sx, double sy, int width, int height,
             double* output, int capacity) {
    if (!handle || n < 0 || sx <= 0 || sy <= 0 || width <= 0 || height <= 0) return -3;
    try {
        auto& w = *static_cast<Workspace*>(handle);
        w.scores.assign(n, -INFINITY);
        w.classes.assign(n, 0);
        w.candidates.clear();
        // Iterate channel-major data directly; avoid a transposed strided reduction.
        bool invalid_range = false;
        for (int c = 0; c < 80; ++c) {
            const T* channel = scores + c*n;
            int64_t i=0;
#ifdef __aarch64__
            if constexpr(std::is_same<T,Half>::value) {
                for(;i+8<=n;i+=8) {
                    auto half=vld1q_f16(reinterpret_cast<const float16_t*>(channel+i));
                    float32x4_t values[2]={vcvt_f32_f16(vget_low_f16(half)),vcvt_f32_f16(vget_high_f16(half))};
                    for(int j=0;j<2;j++) {
                        auto value=values[j];auto offset=i+j*4;
                        if(vminvq_u32(vcleq_f32(vabsq_f32(value),vdupq_n_f32(__FLT_MAX__)))==0)return -1;
                        // Bounds are supplied as exact FP32 or FP16 scalar values.
                        invalid_range |= vmaxvq_u32(vorrq_u32(vcltq_f32(value,vdupq_n_f32(float(low))),
                                                              vcgtq_f32(value,vdupq_n_f32(float(high)))))!=0;
                        auto old=vld1q_f32(w.scores.data()+offset);auto take=vcgtq_f32(value,old);
                        vst1q_f32(w.scores.data()+offset,vbslq_f32(take,value,old));
                        auto cls=vld1q_s32(w.classes.data()+offset);
                        vst1q_s32(w.classes.data()+offset,vbslq_s32(take,vdupq_n_s32(c),cls));
                    }
                }
            }
#endif
            for (; i < n; ++i) {
                const float value = channel[i];
                if (!std::isfinite(value)) return -1;
                invalid_range |= value < low || value > high;
                if (value > w.scores[i]) { w.scores[i] = value; w.classes[i] = c; }
            }
        }
        for (int64_t i = 0; i < 4*n; ++i) if (!std::isfinite(float(boxes[i]))) return -1;
        if (invalid_range) return -2;
        for (int64_t i = 0; i < n; ++i) if (w.scores[i] > threshold) w.candidates.push_back(i);
        const int64_t count = static_cast<int64_t>(w.candidates.size());
        const int64_t keep = topk < 0 ? std::max<int64_t>(0, count+topk) : std::min(count, topk);
        if (keep > capacity) return -3;
        std::partial_sort(w.candidates.begin(), w.candidates.begin()+keep, w.candidates.end(),
            [&](int64_t a, int64_t b) {
                return w.scores[a] == w.scores[b] ? a < b : w.scores[a] > w.scores[b];
            });
        int result = 0;
        for (int64_t k = 0; k < keep; ++k) {
            const auto i = w.candidates[k];
            double xy[4];
            for (int c = 0; c < 4; ++c) {
                double value = (static_cast<double>(float(boxes[c*n+i]))-(c%2 ? top : left))/(c%2 ? sy : sx);
                const double limit = c%2 ? height : width;
                xy[c] = value <= 0 ? 0. : std::min(value, limit);
            }
            // TopK precedes dropping invalid boxes, as in the reference.
            if (xy[2] <= xy[0] || xy[3] <= xy[1]) continue;
            double* row = output + result++*6;
            row[0] = w.classes[i]; row[1] = w.scores[i];
            std::copy(xy, xy+4, row+2);
        }
        return result;
    } catch (...) { return -3; }
}
extern "C" {
int post_abi_version() { return 2; }
void* post_create() { try { return new Workspace; } catch (...) { return nullptr; } }
void post_destroy(void* p) { delete static_cast<Workspace*>(p); }
#define PARAMS void* h,const void* s,const void* b,int64_t n,double lo,double hi,double th,int64_t k,\
 double l,double t,double sx,double sy,int w,int ht,double* o,int cap
#define ARGS h,static_cast<const TYPE*>(s),static_cast<const TYPE*>(b),n,lo,hi,th,k,l,t,sx,sy,w,ht,o,cap
#define TYPE float
int post_run(PARAMS) { return run(ARGS); }
#undef TYPE
#define TYPE Half
int post_run_half(PARAMS) { return run(ARGS); }
#undef TYPE
#undef PARAMS
#undef ARGS
}
