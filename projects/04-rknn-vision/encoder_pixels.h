// SPDX-License-Identifier: AGPL-3.0-only
#pragma once
#include <arm_neon.h>
#include <cstdint>
namespace output_pixels {
inline uint8x16_t luma(const uint8x16x3_t& bgr){
    auto one=[&](bool hi){
        auto b=hi?vget_high_u8(bgr.val[0]):vget_low_u8(bgr.val[0]);
        auto g=hi?vget_high_u8(bgr.val[1]):vget_low_u8(bgr.val[1]);
        auto r=hi?vget_high_u8(bgr.val[2]):vget_low_u8(bgr.val[2]);
        auto sum=vmull_u8(b,vdup_n_u8(25));sum=vmlal_u8(sum,g,vdup_n_u8(129));sum=vmlal_u8(sum,r,vdup_n_u8(66));
        return vadd_u8(vshrn_n_u16(vaddq_u16(sum,vdupq_n_u16(128)),8),vdup_n_u8(16));
    };
    return vcombine_u8(one(false),one(true));
}
inline void convert(const uint8_t* src,int stride,uint8_t* y,uint8_t* uv,int width,int height,int hs){
    for(int row=0;row<height;row+=2)for(int x=0;x<width;x+=16){
        auto a=vld3q_u8(src+size_t(row)*stride+x*3),b=vld3q_u8(src+size_t(row+1)*stride+x*3);
        vst1q_u8(y+size_t(row)*hs+x,luma(a));vst1q_u8(y+size_t(row+1)*hs+x,luma(b));
        int16x8_t rgb[3];
        for(int c=0;c<3;c++)rgb[c]=vreinterpretq_s16_u16(vshrq_n_u16(vaddq_u16(vaddq_u16(vpaddlq_u8(a.val[c]),vpaddlq_u8(b.val[c])),vdupq_n_u16(2)),2));
        auto u=vmulq_n_s16(rgb[0],112);u=vmlaq_n_s16(u,rgb[1],-74);u=vmlaq_n_s16(u,rgb[2],-38);
        auto v=vmulq_n_s16(rgb[0],-18);v=vmlaq_n_s16(v,rgb[1],-94);v=vmlaq_n_s16(v,rgb[2],112);
        uint8x8x2_t pair;
        pair.val[0]=vqmovun_s16(vaddq_s16(vshrq_n_s16(vaddq_s16(u,vdupq_n_s16(128)),8),vdupq_n_s16(128)));
        pair.val[1]=vqmovun_s16(vaddq_s16(vshrq_n_s16(vaddq_s16(v,vdupq_n_s16(128)),8),vdupq_n_s16(128)));
        vst2_u8(uv+size_t(row/2)*hs+x,pair);
    }
}
}
