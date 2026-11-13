// SPDX-License-Identifier: AGPL-3.0-only
// Small synchronous C ABI. No model, input-normalization or precision changes.
#include "third_party/rknn_api.h"
#include <dlfcn.h>
#include <time.h>
#include <algorithm>
#include <cstdio>
#include <cstring>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
#include <array>

namespace {
double clock_ms(clockid_t id) {
    timespec t{};
    if (clock_gettime(id, &t)) throw std::runtime_error("clock_gettime failed");
    return t.tv_sec * 1000.0 + t.tv_nsec / 1e6;
}
void checked(int rc, const char* op) {
    if (rc != RKNN_SUCC) throw std::runtime_error(std::string(op)+": "+std::to_string(rc));
}
template<typename T> T symbol(void* lib, const char* name) {
    auto p = reinterpret_cast<T>(dlsym(lib,name));
    if (!p) throw std::runtime_error(std::string("Missing Runtime symbol: ")+name);
    return p;
}
const std::array<uint16_t,256>& normalization_table() {
    static const auto table=[] {
        std::array<uint16_t,256> values{};
        for(unsigned i=1;i<values.size();i++) {
            // Positive FP32 x/255 is normal in FP16 for every nonzero UINT8.
            // Round to nearest, ties to even, without platform half extensions.
            float value=static_cast<float>(i)/255.0f;
            uint32_t bits; std::memcpy(&bits,&value,sizeof(bits));
            const uint32_t rounded=bits+0xfffu+((bits>>13)&1u);
            values[i]=static_cast<uint16_t>((rounded>>13)-(112u<<10));
        }
        return values;
    }();
    return table;
}
struct Session {
    void* lib = nullptr;
    rknn_context ctx = 0;
    decltype(&rknn_init) init;
    decltype(&rknn_destroy) destroy = nullptr;
    decltype(&rknn_query) query;
    decltype(&rknn_set_core_mask) core;
    decltype(&rknn_inputs_set) inputs;
    decltype(&rknn_run) run;
    decltype(&rknn_outputs_get) get;
    decltype(&rknn_outputs_release) release;
    rknn_tensor_attr attrs[2]{};
    bool fp16_pass=false;
    bool fp16_ready=false;
    bool fp16_output=false;
    bool collect_perf=false;
    unsigned init_flags=0;
    std::vector<uint16_t> fp16_input;
    std::string metadata;
    ~Session() { if(ctx && destroy) destroy(ctx); if(lib) dlclose(lib); }
};
void error(char* dest, unsigned capacity, const char* message) {
    if(dest && capacity) std::snprintf(dest,capacity,"%s",message);
}
std::string attr_json(const rknn_tensor_attr& a) {
    std::ostringstream out;
    out << "{\"index\":" << a.index << ",\"elements\":" << a.n_elems
        << ",\"type\":" << int(a.type) << ",\"format\":" << int(a.fmt)
        << ",\"size\":" << a.size << ",\"size_with_stride\":" << a.size_with_stride
        << ",\"w_stride\":" << a.w_stride << ",\"dims\":[";
    for(unsigned i=0;i<a.n_dims;i++) { if(i) out << ','; out << a.dims[i]; }
    out << "]}";
    return out.str();
}
}

extern "C" {
// C/Python layout: wall and CPU for set/run/get/copy/release, SDK duration, query rc.
struct nr_timing {
    double wall[5]; double cpu[5]; double device_ms; int query_rc;
    double normalize_wall_ms; double normalize_cpu_ms;
};

int nr_lut(uint16_t* destination, unsigned count) {
    if(!destination || count!=256) return -1;
    std::memcpy(destination,normalization_table().data(),256*sizeof(uint16_t));
    return 0;
}

void* nr_create(const char* library, const char* model, int mask, int input_mode, char* err, unsigned capacity) {
    try {
        auto s = std::make_unique<Session>();
        s->lib = dlopen(library,RTLD_NOW|RTLD_LOCAL);
        if(!s->lib) throw std::runtime_error(dlerror());
#define LOAD(member, name) s->member=symbol<decltype(s->member)>(s->lib,#name)
        LOAD(init,rknn_init); LOAD(destroy,rknn_destroy); LOAD(query,rknn_query);
        LOAD(core,rknn_set_core_mask); LOAD(inputs,rknn_inputs_set); LOAD(run,rknn_run);
        LOAD(get,rknn_outputs_get); LOAD(release,rknn_outputs_release);
#undef LOAD
        const unsigned flags=((input_mode&32)?RKNN_FLAG_DISABLE_FLUSH_INPUT_MEM_CACHE:0)|
                             ((input_mode&64)?RKNN_FLAG_DISABLE_FLUSH_OUTPUT_MEM_CACHE:0)|
                             ((input_mode&128)?RKNN_FLAG_COLLECT_PERF_MASK:0);
        s->init_flags=flags;
        s->collect_perf=(input_mode&128)!=0;
        checked(s->init(&s->ctx,const_cast<char*>(model),0,flags,nullptr),"rknn_init");
        checked(s->core(s->ctx,static_cast<rknn_core_mask>(mask)),"rknn_set_core_mask");
        rknn_input_output_num num{};
        checked(s->query(s->ctx,RKNN_QUERY_IN_OUT_NUM,&num,sizeof(num)),"query I/O count");
        if(num.n_input!=1 || num.n_output!=2) throw std::runtime_error("Expected one input and two full outputs");
        rknn_tensor_attr input{};
        checked(s->query(s->ctx,RKNN_QUERY_INPUT_ATTR,&input,sizeof(input)),"query input");
        if(input.n_elems!=640*640*3) throw std::runtime_error("Native backend requires batch=1, 640x640 RGB");
        rknn_tensor_attr native_input{};
        checked(s->query(s->ctx,RKNN_QUERY_NATIVE_INPUT_ATTR,&native_input,sizeof(native_input)),"query native input");
        s->fp16_output=(input_mode&16)!=0;
        const int fp16_pass=input_mode&15;
        s->fp16_pass=fp16_pass!=0;
        s->fp16_ready=fp16_pass==2;
        if(s->fp16_pass) {
            if(native_input.type!=RKNN_TENSOR_FLOAT16 || native_input.fmt!=RKNN_TENSOR_NHWC ||
               native_input.n_dims!=4 || native_input.dims[0]!=1 || native_input.dims[1]!=640 ||
               native_input.dims[2]!=640 || native_input.dims[3]!=3 ||
               native_input.n_elems!=640*640*3 || native_input.size!=2457600 ||
               native_input.size_with_stride!=2457600 || native_input.w_stride!=640)
                throw std::runtime_error("FP16 pass-through requires packed [1,640,640,3] native NHWC, stride=640");
            if(!s->fp16_ready)s->fp16_input.resize(native_input.n_elems);
            normalization_table();
        }
        for(unsigned i=0;i<2;i++) {
            s->attrs[i].index=i;
            checked(s->query(s->ctx,RKNN_QUERY_OUTPUT_ATTR,&s->attrs[i],sizeof(s->attrs[i])),"query output");
            if(s->fp16_output && (s->attrs[i].type!=RKNN_TENSOR_FLOAT16 ||
                s->attrs[i].size!=s->attrs[i].n_elems*2))
                throw std::runtime_error("FP16 output requires packed native FP16 scores/boxes");
        }
        rknn_sdk_version version{};
        checked(s->query(s->ctx,RKNN_QUERY_SDK_VERSION,&version,sizeof(version)),"query SDK");
        s->metadata=std::string("{\"api_version\":\"")+version.api_version+"\",\"driver_version\":\""+
            version.drv_version+"\",\"init_flags\":"+std::to_string(flags)+",\"core_mask\":"+std::to_string(mask)+
            ",\"input\":"+attr_json(input)+",\"native_input\":"+attr_json(native_input)+
            ",\"input_mode\":\""+(s->fp16_ready?"fp16-ready":s->fp16_pass?"fp16-pass":"uint8")+"\",\"outputs\":["+
            attr_json(s->attrs[0])+","+attr_json(s->attrs[1])+
            "],\"input_submission\":\""+(s->fp16_ready?"caller-owned prepared FP16 NHWC pass_through=1":s->fp16_pass?"FP16 NHWC pass_through=1; FP32 x/255 to FP16 RNE LUT":
            "UINT8 NHWC pass_through=0")+"\",\"output_request\":\"want_float="+(s->fp16_output?"0":"1")+"\"}";
        return s.release();
    } catch(const std::exception& e) { error(err,capacity,e.what()); return nullptr; }
}
const char* nr_metadata(void* handle) { return static_cast<Session*>(handle)->metadata.c_str(); }
void nr_destroy(void* handle) { delete static_cast<Session*>(handle); }

int nr_infer(void* handle, const void* rgb, unsigned input_bytes, void* dst0, unsigned bytes0,
             void* dst1, unsigned bytes1, int prealloc, int profile, nr_timing* timing,
             char* err, unsigned capacity,char* detail_buffer,unsigned detail_capacity,
             unsigned* detail_size,int* detail_query_rc) {
    Session* s=static_cast<Session*>(handle);
    rknn_output outputs[2]{};
    bool acquired=false;
    std::memset(timing,0,sizeof(*timing));
    timing->device_ms=-1.; timing->query_rc=-999;
    if(detail_size)*detail_size=0;
    if(detail_query_rc)*detail_query_rc=-999;
    if(detail_buffer && detail_capacity)detail_buffer[0]='\0';
    try {
        if(input_bytes!=640*640*3*(s->fp16_ready?2:1) || !rgb || !dst0 || !dst1 ||
           bytes0!=s->attrs[0].n_elems*(s->fp16_output?2:4) || bytes1!=s->attrs[1].n_elems*(s->fp16_output?2:4))
            throw std::runtime_error("Input/output buffer size mismatch");
        auto measure=[&](unsigned index, auto operation) {
            const double wall=clock_ms(CLOCK_MONOTONIC), cpu=clock_ms(CLOCK_THREAD_CPUTIME_ID);
            const int rc=operation();
            timing->cpu[index]=clock_ms(CLOCK_THREAD_CPUTIME_ID)-cpu;
            timing->wall[index]=clock_ms(CLOCK_MONOTONIC)-wall;
            return rc;
        };
        rknn_input input{};
        input.buf=const_cast<void*>(rgb); input.size=input_bytes;
        input.type=RKNN_TENSOR_UINT8; input.fmt=RKNN_TENSOR_NHWC; input.pass_through=0;
        if(s->fp16_ready) {
            input.type=RKNN_TENSOR_FLOAT16;input.pass_through=1;
        } else if(s->fp16_pass) {
            const double wall=clock_ms(CLOCK_MONOTONIC), cpu=clock_ms(CLOCK_THREAD_CPUTIME_ID);
            const auto& lut=normalization_table();
            const uint8_t* source=static_cast<const uint8_t*>(rgb);
            for(unsigned i=0;i<input_bytes;i++) s->fp16_input[i]=lut[source[i]];
            timing->normalize_cpu_ms=clock_ms(CLOCK_THREAD_CPUTIME_ID)-cpu;
            timing->normalize_wall_ms=clock_ms(CLOCK_MONOTONIC)-wall;
            input.buf=s->fp16_input.data(); input.size=s->fp16_input.size()*sizeof(uint16_t);
            input.type=RKNN_TENSOR_FLOAT16; input.pass_through=1;
        }
        checked(measure(0,[&]{return s->inputs(s->ctx,1,&input);}),"rknn_inputs_set");
        checked(measure(1,[&]{return s->run(s->ctx,nullptr);}),"rknn_run");
        void* destinations[2]={dst0,dst1}; unsigned sizes[2]={bytes0,bytes1};
        for(unsigned i=0;i<2;i++) {
            outputs[i].index=i; outputs[i].want_float=!s->fp16_output; outputs[i].is_prealloc=prealloc!=0;
            if(prealloc) { outputs[i].buf=destinations[i]; outputs[i].size=sizes[i]; }
        }
        const int get_rc=measure(2,[&]{return s->get(s->ctx,2,outputs,nullptr);});
        // Release any partial Runtime allocation on an error too.
        acquired=get_rc==0 || (!prealloc && (outputs[0].buf || outputs[1].buf));
        checked(get_rc,"rknn_outputs_get");
        for(unsigned i=0;i<2;i++)
            if(!outputs[i].buf || outputs[i].size!=sizes[i])throw std::runtime_error("Unexpected logical output size");
        if(profile) {
            rknn_perf_run perf{};
            timing->query_rc=s->query(s->ctx,RKNN_QUERY_PERF_RUN,&perf,sizeof(perf));
            if(timing->query_rc==0 && perf.run_duration>=0) timing->device_ms=perf.run_duration/1000.;
            if(s->collect_perf && detail_buffer && detail_capacity && detail_size && detail_query_rc) {
                rknn_perf_detail detail{};
                *detail_query_rc=s->query(s->ctx,RKNN_QUERY_PERF_DETAIL,&detail,sizeof(detail));
                if(*detail_query_rc==RKNN_SUCC && detail.perf_data && detail.data_len) {
                    *detail_size=static_cast<unsigned>(detail.data_len);
                    const unsigned copied=std::min(detail_capacity-1,*detail_size);
                    std::memcpy(detail_buffer,detail.perf_data,copied);
                    detail_buffer[copied]='\0';
                }
            }
        }
        if(!prealloc) measure(3,[&]{
            for(unsigned i=0;i<2;i++) {
                if(!outputs[i].buf || outputs[i].size!=sizes[i]) throw std::runtime_error("Unexpected float output size");
                std::memcpy(destinations[i],outputs[i].buf,sizes[i]);
            }
            return 0;
        });
        const int release_rc=measure(4,[&]{return s->release(s->ctx,2,outputs);});
        acquired=false;
        checked(release_rc,"rknn_outputs_release");
        return 0;
    } catch(const std::exception& e) {
        if(acquired) s->release(s->ctx,2,outputs);
        error(err,capacity,e.what()); return -1;
    }
}
}

// Bound memory belongs to this context until all Python leases are returned.
struct BoundMemory {
    Session* s; bool both; bool fixed; int slots; double fixed_bind_ms=0.; std::string metadata;
    decltype(&rknn_create_mem2) create;
    decltype(&rknn_destroy_mem) destroy;
    decltype(&rknn_set_io_mem) bind;
    decltype(&rknn_mem_sync) sync;
    rknn_tensor_attr input{}, output[2]{};
    std::vector<rknn_tensor_mem*> inputs;
    std::vector<std::array<rknn_tensor_mem*,2>> outputs;
    ~BoundMemory() {
        for(auto m:inputs)if(m)destroy(s->ctx,m);
        for(auto& slot:outputs)for(auto tensor:slot)if(tensor)destroy(s->ctx,tensor);
    }
};
extern "C" {
void* nr_bound_create(void* handle,int both,int slots,int fixed,char* err,unsigned cap) {
    try {
        if(slots<1 || slots>8 || (fixed && (!both || slots!=1)))
            throw std::runtime_error("Invalid bound I/O pool shape");
        auto b=std::make_unique<BoundMemory>();b->s=static_cast<Session*>(handle);b->both=both;b->slots=slots;b->fixed=fixed!=0;
        auto s=b->s;
        b->inputs.resize(slots,nullptr);
        if(both)b->outputs.resize(slots,std::array<rknn_tensor_mem*,2>{nullptr,nullptr});
        b->create=symbol<decltype(b->create)>(s->lib,"rknn_create_mem2");
        b->destroy=symbol<decltype(b->destroy)>(s->lib,"rknn_destroy_mem");
        b->bind=symbol<decltype(b->bind)>(s->lib,"rknn_set_io_mem");
        b->sync=symbol<decltype(b->sync)>(s->lib,"rknn_mem_sync");
        checked(s->query(s->ctx,RKNN_QUERY_NATIVE_INPUT_ATTR,&b->input,sizeof(b->input)),"bound input attr");
        b->input.pass_through=1;
        for(int j=0;j<slots;j++) {
            b->inputs[j]=b->create(s->ctx,b->input.size_with_stride,RKNN_FLAG_MEMORY_CACHEABLE);
            if(!b->inputs[j] || !b->inputs[j]->virt_addr)throw std::runtime_error("bound input allocation failed");
            std::memset(b->inputs[j]->virt_addr,0,b->inputs[j]->size);
        }
        if(!both)for(int i=0;i<2;i++) {
            b->output[i].index=i;
            checked(s->query(s->ctx,RKNN_QUERY_NATIVE_OUTPUT_ATTR,&b->output[i],sizeof(b->output[i])),"copy output allocation attr");
        }
        if(both)for(int i=0;i<2;i++) {
            auto& a=b->output[i];a.index=i;
            checked(s->query(s->ctx,RKNN_QUERY_NATIVE_NHWC_OUTPUT_ATTR,&a,sizeof(a)),"bound native NHWC output attr");
            if(a.type!=RKNN_TENSOR_FLOAT16 || a.n_dims!=3 || a.dims[0]!=1 ||
               a.dims[2]!=8400 || (a.dims[1]!=4 && a.dims[1]!=80) ||
               a.size!=a.n_elems*2 || a.size_with_stride!=a.size)
                throw std::runtime_error("Unsupported bound output layout; no implicit truncation/conversion");
            for(int j=0;j<slots;j++) {
                b->outputs[j][i]=b->create(s->ctx,a.size_with_stride,RKNN_FLAG_MEMORY_CACHEABLE);
                if(!b->outputs[j][i] || !b->outputs[j][i]->virt_addr)throw std::runtime_error("bound output allocation failed");
            }
        }
        if(b->fixed) {
            const double begin=clock_ms(CLOCK_MONOTONIC);
            checked(b->bind(s->ctx,b->inputs[0],&b->input),"fixed bind input");
            for(int i=0;i<2;i++)checked(b->bind(s->ctx,b->outputs[0][i],&b->output[i]),"fixed bind output");
            b->fixed_bind_ms=clock_ms(CLOCK_MONOTONIC)-begin;
        }
        b->metadata=std::string("{\"input\":")+attr_json(b->input)+",\"outputs\":["+(attr_json(b->output[0])+","+attr_json(b->output[1]))+
            "],\"slots\":"+std::to_string(slots)+",\"fixed_binding\":"+(b->fixed?"true":"false")+
            ",\"fixed_bind_init_ms\":"+std::to_string(b->fixed_bind_ms)+"}";
        return b.release();
    }catch(const std::exception& e){error(err,cap,e.what());return nullptr;}
}
const char* nr_bound_metadata(void* h){return static_cast<BoundMemory*>(h)->metadata.c_str();}
void nr_bound_destroy(void* h){delete static_cast<BoundMemory*>(h);}
void* nr_bound_ptr(void* h,int slot,int tensor) {
    auto b=static_cast<BoundMemory*>(h);
    if(slot<0 || slot>=b->slots || tensor<0 || tensor>2)return nullptr;
    auto m=tensor==0?b->inputs[slot]:(b->both?b->outputs[slot][tensor-1]:nullptr);
    return m?m->virt_addr:nullptr;
}
int nr_bound_run(void* h,int in_slot,int out_slot,void* dst0,unsigned bytes0,void* dst1,unsigned bytes1,
                 double* wall,double* cpu,char* err,unsigned cap) {
    // bind-input, sync-to, run, bind-output, sync-from, get-output, layout.
    for(int i=0;i<7;i++)wall[i]=cpu[i]=-1.;
    try {
        auto b=static_cast<BoundMemory*>(h);auto s=b->s;
        if(in_slot<0 || in_slot>=b->slots || out_slot<0 || out_slot>=b->slots)throw std::runtime_error("Invalid bound slot");
        auto measure=[&](int i,auto operation){auto w=clock_ms(CLOCK_MONOTONIC),c=clock_ms(CLOCK_THREAD_CPUTIME_ID);
            int rc=operation();wall[i]=clock_ms(CLOCK_MONOTONIC)-w;cpu[i]=clock_ms(CLOCK_THREAD_CPUTIME_ID)-c;checked(rc,"bound operation");};
        if(!b->fixed)measure(0,[&]{return b->bind(s->ctx,b->inputs[in_slot],&b->input);});
        measure(1,[&]{return b->sync(s->ctx,b->inputs[in_slot],RKNN_MEMORY_SYNC_TO_DEVICE);});
        if(b->both && !b->fixed)measure(3,[&]{for(int i=0;i<2;i++)checked(b->bind(s->ctx,b->outputs[out_slot][i],&b->output[i]),"bind output");return 0;});
        measure(2,[&]{return s->run(s->ctx,nullptr);});
        if(b->both) {
            measure(4,[&]{for(int i=0;i<2;i++)checked(b->sync(s->ctx,b->outputs[out_slot][i],RKNN_MEMORY_SYNC_FROM_DEVICE),"sync output");return 0;});
            wall[6]=cpu[6]=0.; // Verified packed native layout; no layout conversion.
        }else {
            rknn_output outputs[2]{};void* dst[2]={dst0,dst1};unsigned size[2]={bytes0,bytes1};
            for(int i=0;i<2;i++){outputs[i].index=i;outputs[i].want_float=0;outputs[i].is_prealloc=1;outputs[i].buf=dst[i];outputs[i].size=size[i];}
            measure(5,[&]{return s->get(s->ctx,2,outputs,nullptr);});
            checked(s->release(s->ctx,2,outputs),"release bound-input outputs");
        }
        return 0;
    }catch(const std::exception& e){error(err,cap,e.what());return -1;}
}
}
