// SPDX-License-Identifier: AGPL-3.0-only
// Test-only C API fixture. Never used by the benchmark launcher.
#include "rknn_api.h"
#include <algorithm>
#include <atomic>
#include <cstring>
#include <mutex>
#include <unordered_map>
#include <array>
#include <cmath>
namespace {
std::atomic<int> buffers{0}, failure{0}, next_id{1};
std::mutex guard;
struct FakeContext { float value=0.f; rknn_tensor_mem* input=nullptr; rknn_tensor_mem* outputs[2]{}; };
std::unordered_map<rknn_context,FakeContext> contexts;
std::array<uint16_t,256> input_half{};
int native_bad=0,last_type=-1,last_pass=-1,last_size=0;
}
extern "C" {
void fixture_fail_stage(int n) { failure=n; }
void fixture_bad_native(int n) { native_bad=n; }
int fixture_input_half(unsigned index) { return input_half.at(index); }
int fixture_input_type() { return last_type; }
int fixture_input_pass() { return last_pass; }
int fixture_input_size() { return last_size; }
int fixture_live_buffers() { return buffers; }
int fixture_live_contexts() { std::lock_guard<std::mutex> g(guard); return contexts.size(); }
int rknn_init(rknn_context* ctx,void*,uint32_t,uint32_t,rknn_init_extend*) {
    std::lock_guard<std::mutex> g(guard); *ctx=next_id++; contexts[*ctx]=FakeContext{}; return 0;
}
int rknn_destroy(rknn_context ctx) { std::lock_guard<std::mutex> g(guard); contexts.erase(ctx); return 0; }
int rknn_set_core_mask(rknn_context,rknn_core_mask) { return 0; }
int rknn_query(rknn_context,rknn_query_cmd cmd,void* data,uint32_t) {
    if(cmd==RKNN_QUERY_IN_OUT_NUM) { auto p=(rknn_input_output_num*)data; p->n_input=1;p->n_output=2; }
    else if(cmd==RKNN_QUERY_INPUT_ATTR || cmd==RKNN_QUERY_NATIVE_INPUT_ATTR || cmd==RKNN_QUERY_OUTPUT_ATTR || cmd==RKNN_QUERY_NATIVE_NHWC_OUTPUT_ATTR) {
        auto p=(rknn_tensor_attr*)data;
        const bool input=cmd==RKNN_QUERY_INPUT_ATTR || cmd==RKNN_QUERY_NATIVE_INPUT_ATTR;
        p->n_dims=input?4:3;p->dims[0]=1;
        p->dims[1]=input?640:p->index==0?80:4;
        p->dims[2]=input?640:8400;p->dims[3]=input?3:0;
        p->n_elems=input?640*640*3:p->dims[1]*8400;
        p->type=RKNN_TENSOR_FLOAT16;p->fmt=input?RKNN_TENSOR_NHWC:RKNN_TENSOR_NCHW;p->size=p->n_elems*2;
        p->w_stride=input?(native_bad?641:640):0;p->size_with_stride=p->size;p->scale=1.f;
    } else if(cmd==RKNN_QUERY_SDK_VERSION) {
        auto p=(rknn_sdk_version*)data;std::strcpy(p->api_version,"fixture");std::strcpy(p->drv_version,"fixture");
    } else if(cmd==RKNN_QUERY_PERF_RUN) { ((rknn_perf_run*)data)->run_duration=1234; }
    else if(cmd==RKNN_QUERY_PERF_DETAIL) {
        static char report[]="0: Conv fixture 1250 us\n1: Reorder fixture 0.5 ms\n";
        auto p=(rknn_perf_detail*)data;p->perf_data=report;p->data_len=std::strlen(report);
    }
    else return -1;
    return 0;
}
int rknn_inputs_set(rknn_context ctx,uint32_t,rknn_input in[]) {
    if(failure==1)return -1;
    std::lock_guard<std::mutex> g(guard);
    last_type=in[0].type;last_pass=in[0].pass_through;last_size=in[0].size;
    if(in[0].pass_through) {
        if(in[0].type!=RKNN_TENSOR_FLOAT16 || in[0].size!=2457600 || in[0].fmt!=RKNN_TENSOR_NHWC)return -1;
        std::memcpy(input_half.data(),in[0].buf,512);
        uint16_t h=input_half[0];
        contexts[ctx].value=h?std::ldexp(float(1024+(h&1023)),int((h>>10)&31)-25):0.f;
    } else contexts[ctx].value=((unsigned char*)in[0].buf)[0]/255.f;
    return 0;
}
int rknn_run(rknn_context ctx,rknn_run_extend*) {
    if(failure==2)return -1;
    std::lock_guard<std::mutex> g(guard);auto& context=contexts[ctx];
    if(context.input) {
        uint16_t h=*(uint16_t*)context.input->virt_addr;
        context.value=h?std::ldexp(float(1024+(h&1023)),int((h>>10)&31)-25):0.f;
    }
    uint32_t bits;std::memcpy(&bits,&context.value,4);bits+=0xfffu+((bits>>13)&1u);
    const uint16_t half=context.value?uint16_t((bits>>13)-(112u<<10)):0;
    for(unsigned i=0;i<2;i++)if(context.outputs[i])
        std::fill((uint16_t*)context.outputs[i]->virt_addr,(uint16_t*)context.outputs[i]->virt_addr+(i==0?80:4)*8400,half);
    return 0;
}
int rknn_outputs_get(rknn_context ctx,uint32_t,rknn_output out[],rknn_output_extend*) {
    float value;{std::lock_guard<std::mutex> g(guard);value=contexts[ctx].value;}
    for(unsigned i=0;i<2;i++) {
        unsigned n=(i==0?80:4)*8400;
        if(!out[i].is_prealloc) { out[i].buf=new unsigned char[n*(out[i].want_float?4:2)];buffers++; }
        out[i].size=n*(out[i].want_float?4:2);
        if(out[i].want_float)std::fill((float*)out[i].buf,(float*)out[i].buf+n,value);
        else {
            uint32_t bits;std::memcpy(&bits,&value,4);bits+=0xfffu+((bits>>13)&1u);
            uint16_t half=value?uint16_t((bits>>13)-(112u<<10)):0;
            std::fill((uint16_t*)out[i].buf,(uint16_t*)out[i].buf+n,half);
        }
        if(failure==3) return -1;
    }
    return 0;
}
int rknn_outputs_release(rknn_context,uint32_t,rknn_output out[]) {
    for(unsigned i=0;i<2;i++)if(!out[i].is_prealloc && out[i].buf) {
        delete[] (unsigned char*)out[i].buf;out[i].buf=nullptr;buffers--;
    }
    return failure==4?-1:0;
}
rknn_tensor_mem* rknn_create_mem2(rknn_context,uint64_t size,uint64_t) {
    auto mem=new rknn_tensor_mem{};mem->virt_addr=new unsigned char[size]{};mem->size=(uint32_t)size;mem->fd=-1;buffers++;return mem;
}
int rknn_destroy_mem(rknn_context,rknn_tensor_mem* mem) {
    delete[] (unsigned char*)mem->virt_addr;delete mem;buffers--;return 0;
}
int rknn_set_io_mem(rknn_context ctx,rknn_tensor_mem* mem,rknn_tensor_attr* attr) {
    std::lock_guard<std::mutex> g(guard);auto& context=contexts[ctx];
    if(attr->n_dims==4)context.input=mem;
    else if(attr->index<2)context.outputs[attr->index]=mem;
    else return -1;
    return 0;
}
int rknn_mem_sync(rknn_context,rknn_tensor_mem*,rknn_mem_sync_mode) { return 0; }
}
