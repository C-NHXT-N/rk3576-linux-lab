// SPDX-License-Identifier: AGPL-3.0-only
// Exact OpenCV 2x averaging, BGR->RGB and normalized FP16 in one source pass.
#include <arm_neon.h>
#include <cstddef>
#include <cstdint>

extern "C" int cp_rows(const uint8_t* source, size_t stride, uint16_t* target,
                       const uint16_t* lut, int rows, int offset) {
    if (!source || !target || !lut || stride < 1280*3) return -1;
    for (int y=0; y<rows; ++y) {
        const auto a=source+2*y*stride, b=a+stride;
        auto out=target+size_t(y+offset)*640*3;
        for (int x=0; x<640; x+=8) {
            auto u=vld3q_u8(a+x*6), v=vld3q_u8(b+x*6);
            uint16x8x3_t rgb;
            for (int c=0; c<3; ++c) {
                auto sum=vaddq_u16(vpaddlq_u8(u.val[c]),vpaddlq_u8(v.val[c]));
                auto pixel=vshrq_n_u16(vaddq_u16(sum,vdupq_n_u16(2)),2);
                auto lo=vmulq_n_f32(vcvtq_f32_u32(vmovl_u16(vget_low_u16(pixel))),1.f/255.f);
                auto hi=vmulq_n_f32(vcvtq_f32_u32(vmovl_u16(vget_high_u16(pixel))),1.f/255.f);
                rgb.val[2-c]=vcombine_u16(vreinterpret_u16_f16(vcvt_f16_f32(lo)),
                                         vreinterpret_u16_f16(vcvt_f16_f32(hi)));
            }
            vst3q_u16(out+x*3,rgb);
        }
    }
    return 0;
}

extern "C" int cp_run(const uint8_t* source,size_t stride,uint16_t* target,const uint16_t* lut) {
    return cp_rows(source,stride,target,lut,360,140);
}

extern "C" int cp_check_lut(const uint16_t* lut) {
    if (!lut) return -1;
    for (unsigned i=0; i<256; ++i) {
        float v=float(i)*(1.f/255.f);
        uint16_t bits=vget_lane_u16(vreinterpret_u16_f16(vcvt_f16_f32(vdupq_n_f32(v))),0);
        if (bits!=lut[i]) return -1;
    }
    return 0;
}
