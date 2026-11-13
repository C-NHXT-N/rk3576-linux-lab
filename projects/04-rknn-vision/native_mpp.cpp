// SPDX-License-Identifier: AGPL-3.0-only
// MPP H.264 decode, reference swscale, caller-owned BGR. No raw-frame IPC.
extern "C" {
#include <libavformat/avformat.h>
#include <libavcodec/bsf.h>
#include <libswscale/swscale.h>
#include <rk_mpi.h>
#include <mpp_buffer.h>
#include <mpp_frame.h>
#include <mpp_packet.h>
}
#include <arm_neon.h>
#include <dlfcn.h>
#include <sys/syscall.h>
#include <unistd.h>
#include <pthread.h>
#include <time.h>
#include <array>
#include <algorithm>
#include <cstring>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <deque>
#include <memory>
#include <mutex>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>
#include <map>
#include "cpu_preprocess.cpp"

namespace {
double ms(clockid_t id) { timespec t{};clock_gettime(id,&t);return t.tv_sec*1000.+t.tv_nsec/1e6; }
void check(int rc,const char* op) { if(rc<0)throw std::runtime_error(std::string(op)+": "+std::to_string(rc)); }
template<class T> T sym(void* lib,const char* name) {
    auto p=reinterpret_cast<T>(dlsym(lib,name));if(!p)throw std::runtime_error(std::string("Missing symbol: ")+name);return p;
}
void* library(const char* path) { auto p=dlopen(path,RTLD_NOW|RTLD_LOCAL);if(!p)throw std::runtime_error(dlerror());return p; }
void error(char* dest,unsigned n,const char* message) { if(dest&&n)std::snprintf(dest,n,"%s",message); }

struct Reader {
    void *format_lib=nullptr,*codec_lib=nullptr,*util_lib=nullptr,*scale_lib=nullptr;
#define FN(name) decltype(&name) p_##name=nullptr
    FN(avformat_open_input);FN(avformat_find_stream_info);FN(avformat_close_input);FN(av_read_frame);
    FN(av_packet_alloc);FN(av_packet_unref);FN(av_packet_free);FN(avcodec_parameters_copy);
    FN(av_bsf_get_by_name);FN(av_bsf_alloc);FN(av_bsf_init);FN(av_bsf_send_packet);FN(av_bsf_receive_packet);FN(av_bsf_free);
    FN(sws_getCachedContext);FN(sws_scale);FN(sws_freeContext);
#undef FN
    AVFormatContext* format=nullptr;AVBSFContext* bsf=nullptr;AVPacket* input=nullptr;
    std::array<AVPacket*,8> packets{};int stream=-1;bool demux_eof=false;
    AVRational timebase{},rate{};int64_t start_pts=0;
    MppCtx ctx=nullptr;MppApi* mpi=nullptr;MppBufferGroup group=nullptr;MppPacket packet=nullptr;
    struct Workspace {
        SwsContext* scale=nullptr;
        SwsContext* tiled_scale=nullptr;
        std::vector<uint8_t> u,v,tile;
        std::array<uint16_t,256> lut{};
    } work;
    std::mutex receive_mutex,prep_mutex;

    std::thread sender;std::mutex mutex;std::condition_variable condition;
    std::atomic<bool> started{false},cancelled{false},closing{false},feed_done{false},eos_seen{false};
    std::atomic<int> sender_tid{0};std::string failure,stats;
    std::atomic<uint64_t> accepted{0},frames{0},retries{0},info_changes{0},put_wall_ns{0},put_cpu_ns{0};
    uint64_t output_index=0;

    void fail(const char* message) {
        {std::lock_guard<std::mutex> lock(mutex);if(failure.empty())failure=message;}
        cancelled=true;condition.notify_all();
    }
    void check_failure() { std::lock_guard<std::mutex> lock(mutex);if(!failure.empty())throw std::runtime_error(failure); }

    bool next_packet(AVPacket* out) {
        for(;;) {
            int rc=p_av_bsf_receive_packet(bsf,out);
            if(rc==0)return true;
            if(rc==AVERROR_EOF)return false;
            if(rc!=AVERROR(EAGAIN))check(rc,"av_bsf_receive_packet");
            if(demux_eof)throw std::runtime_error("Bitstream filter stalled after EOS");
            for(;;) {
                rc=p_av_read_frame(format,input);
                if(rc==AVERROR_EOF) {
                    check(p_av_bsf_send_packet(bsf,nullptr),"flush bitstream filter");demux_eof=true;break;
                }
                check(rc,"av_read_frame");
                if(input->stream_index==stream) {
                    int sent=p_av_bsf_send_packet(bsf,input);p_av_packet_unref(input);
                    check(sent,"av_bsf_send_packet");break;
                }
                p_av_packet_unref(input);
            }
        }
    }

    bool put(AVPacket* p,bool eos) {
        void* data=p?p->data:nullptr;size_t size=p?p->size:0;
        if(!packet)check(mpp_packet_init(&packet,data,size),"mpp_packet_init");
        mpp_packet_set_data(packet,data);mpp_packet_set_size(packet,size);
        mpp_packet_set_pos(packet,data);mpp_packet_set_length(packet,size);
        if(eos)check(mpp_packet_set_eos(packet),"mpp_packet_set_eos");
        else {
            if(p->pts==AV_NOPTS_VALUE)throw std::runtime_error("Video packet has no PTS");
            mpp_packet_set_pts(packet,p->pts);
        }
        double deadline=ms(CLOCK_MONOTONIC)+10000.;
        while(!cancelled) {
            double wall=ms(CLOCK_MONOTONIC),cpu=ms(CLOCK_THREAD_CPUTIME_ID);
            int rc=mpi->decode_put_packet(ctx,packet);
            put_wall_ns.fetch_add(uint64_t((ms(CLOCK_MONOTONIC)-wall)*1e6));
            put_cpu_ns.fetch_add(uint64_t((ms(CLOCK_THREAD_CPUTIME_ID)-cpu)*1e6));
            if(rc==MPP_OK) {if(!eos)accepted++;return true;}
            if(rc!=MPP_ERR_TIMEOUT && rc!=MPP_ERR_BUFFER_FULL)check(rc,"decode_put_packet");
            retries++;
            if(ms(CLOCK_MONOTONIC)>deadline)throw std::runtime_error("MPP packet submission timed out");
            std::unique_lock<std::mutex> lock(mutex);
            condition.wait_for(lock,std::chrono::milliseconds(1),[&]{return cancelled.load();});
        }
        return false;
    }

    void submit() {
        pthread_setname_np(pthread_self(),"mpp-submit");sender_tid=syscall(SYS_gettid);condition.notify_all();
        {
            std::unique_lock<std::mutex> lock(mutex);
            condition.wait(lock,[&]{return started.load()||cancelled.load();});
        }
        try {
            std::deque<unsigned> free,pending;for(unsigned i=0;i<8;i++)free.push_back(i);
            bool eof=false;
            while(!cancelled && (!eof || !pending.empty())) {
                while(!cancelled && !eof && !free.empty()) {
                    unsigned slot=free.front();free.pop_front();
                    if(next_packet(packets[slot]))pending.push_back(slot);
                    else {free.push_back(slot);eof=true;}
                }
                if(!pending.empty() && !cancelled) {
                    unsigned slot=pending.front();pending.pop_front();
                    if(!put(packets[slot],false))break;
                    p_av_packet_unref(packets[slot]);free.push_back(slot);
                }
            }
            if(!cancelled)put(nullptr,true);
        } catch(const std::exception& e) {fail(e.what());}
        feed_done=true;condition.notify_all();
        // Preserve the native TID for the matched end-of-measurement CPU ledger.
        std::unique_lock<std::mutex> lock(mutex);condition.wait(lock,[&]{return closing.load();});
    }

    void cancel() {
        cancelled=true;condition.notify_all();
        if(sender.joinable()) {
            std::unique_lock<std::mutex> lock(mutex);
            condition.wait_for(lock,std::chrono::seconds(2),[&]{return feed_done.load();});
        }
    }
    ~Reader() {
        cancel();closing=true;condition.notify_all();if(sender.joinable())sender.join();
        if(ctx)mpp_destroy(ctx);
        if(packet)mpp_packet_deinit(&packet);
        if(group)mpp_buffer_group_put(group);
        if(work.scale)p_sws_freeContext(work.scale);
        if(work.tiled_scale)p_sws_freeContext(work.tiled_scale);
        if(bsf)p_av_bsf_free(&bsf);
        if(input)p_av_packet_free(&input);
        for(auto& p:packets)if(p)p_av_packet_free(&p);
        if(format)p_avformat_close_input(&format);
        if(scale_lib)dlclose(scale_lib);if(format_lib)dlclose(format_lib);
        if(codec_lib)dlclose(codec_lib);if(util_lib)dlclose(util_lib);
    }
};

struct Frame {
    MppFrame value=nullptr;
    ~Frame(){if(value)mpp_frame_deinit(&value);}
};
}

extern "C" {
struct mp_timing { double wall[5];double cpu[5];int64_t pts;double prepare_wall,prepare_cpu; };

void* mp_open(const char* path,const char* format,const char* codec,const char* util,const char* scale,char* err,unsigned cap) {
    try {
        auto r=std::make_unique<Reader>();
        r->util_lib=library(util);r->codec_lib=library(codec);r->format_lib=library(format);r->scale_lib=library(scale);
        if(sym<unsigned(*)()>(r->codec_lib,"avcodec_version")()!=AV_VERSION_INT(59,37,100) ||
           sym<unsigned(*)()>(r->format_lib,"avformat_version")()!=AV_VERSION_INT(59,27,100) ||
           sym<unsigned(*)()>(r->util_lib,"avutil_version")()!=AV_VERSION_INT(57,28,100) ||
           sym<unsigned(*)()>(r->scale_lib,"swscale_version")()!=AV_VERSION_INT(6,7,100))
            throw std::runtime_error("MPP reader requires the pinned reference OpenCV FFmpeg libraries");
#define LOAD(lib,name) r->p_##name=sym<decltype(r->p_##name)>(r->lib##_lib,#name)
        LOAD(format,avformat_open_input);LOAD(format,avformat_find_stream_info);LOAD(format,avformat_close_input);LOAD(format,av_read_frame);
        LOAD(codec,av_packet_alloc);LOAD(codec,av_packet_unref);LOAD(codec,av_packet_free);LOAD(codec,avcodec_parameters_copy);
        LOAD(codec,av_bsf_get_by_name);LOAD(codec,av_bsf_alloc);LOAD(codec,av_bsf_init);LOAD(codec,av_bsf_send_packet);
        LOAD(codec,av_bsf_receive_packet);LOAD(codec,av_bsf_free);
        LOAD(scale,sws_getCachedContext);LOAD(scale,sws_scale);LOAD(scale,sws_freeContext);
#undef LOAD
        check(r->p_avformat_open_input(&r->format,path,nullptr,nullptr),"avformat_open_input");
        check(r->p_avformat_find_stream_info(r->format,nullptr),"avformat_find_stream_info");
        for(unsigned i=0;i<r->format->nb_streams;i++)if(r->format->streams[i]->codecpar->codec_type==AVMEDIA_TYPE_VIDEO){r->stream=i;break;}
        if(r->stream<0)throw std::runtime_error("No video stream");
        auto stream=r->format->streams[r->stream];auto params=stream->codecpar;
        if(params->codec_id!=AV_CODEC_ID_H264 || params->width!=1280 || params->height!=720)
            throw std::runtime_error("MPP reader requires 1280x720 H.264");
        r->timebase=stream->time_base;r->rate=stream->avg_frame_rate;r->start_pts=stream->start_time;
        if(r->start_pts==AV_NOPTS_VALUE || r->rate.num<=0 || r->rate.den<=0)throw std::runtime_error("Missing fixed video timestamp contract");
        auto filter=r->p_av_bsf_get_by_name("h264_mp4toannexb");if(!filter)throw std::runtime_error("h264_mp4toannexb missing");
        check(r->p_av_bsf_alloc(filter,&r->bsf),"av_bsf_alloc");
        check(r->p_avcodec_parameters_copy(r->bsf->par_in,params),"copy bitstream parameters");r->bsf->time_base_in=r->timebase;
        check(r->p_av_bsf_init(r->bsf),"av_bsf_init");
        r->input=r->p_av_packet_alloc();if(!r->input)throw std::bad_alloc();
        for(auto& p:r->packets){p=r->p_av_packet_alloc();if(!p)throw std::bad_alloc();}
        check(mpp_create(&r->ctx,&r->mpi),"mpp_create");
        RK_U32 split=0;check(r->mpi->control(r->ctx,MPP_DEC_SET_PARSER_SPLIT_MODE,&split),"set complete-packet parser");
        check(mpp_init(r->ctx,MPP_CTX_DEC,MPP_VIDEO_CodingAVC),"mpp_init AVC");
        RK_S64 timeout=20;
        check(r->mpi->control(r->ctx,MPP_SET_INPUT_TIMEOUT,&timeout),"set input timeout");
        check(r->mpi->control(r->ctx,MPP_SET_OUTPUT_TIMEOUT,&timeout),"set output timeout");
        MppFrameFormat fmt=MPP_FMT_YUV420SP;
        check(r->mpi->control(r->ctx,MPP_DEC_SET_OUTPUT_FORMAT,&fmt),"set linear NV12");

        r->work.u.resize(640*360+64);r->work.v.resize(640*360+64);
        r->work.tile.resize(1280*24*3+96);
        for(unsigned i=0;i<256;i++){__fp16 value=float(i)*(1.f/255.f);std::memcpy(&r->work.lut[i],&value,2);}
        r->sender=std::thread([p=r.get()]{p->submit();});
        {std::unique_lock<std::mutex> lock(r->mutex);r->condition.wait(lock,[&]{return r->sender_tid.load()!=0;});}
        return r.release();
    }catch(const std::exception& e){error(err,cap,e.what());return nullptr;}
}

int read_impl(void* handle,uint8_t* target,size_t bytes,mp_timing* timing,char* err,unsigned cap,Reader::Workspace& w,uint16_t* fp16=nullptr,bool clear_padding=true) {
    try {
        auto& r=*static_cast<Reader*>(handle);*timing={};
        if((!target && !fp16) || (target && bytes<size_t(1280)*720*3+64))throw std::runtime_error("BGR destination needs SIMD padding");
        std::unique_lock<std::mutex> receive_lock(r.receive_mutex);
        r.check_failure();if(r.cancelled)return 2;if(r.eos_seen)return 0;
        r.started=true;r.condition.notify_all();
        double begin=ms(CLOCK_MONOTONIC),cpu=ms(CLOCK_THREAD_CPUTIME_ID);Frame frame;
        for(;;) {
            r.check_failure();if(r.cancelled)return 2;
            int rc=r.mpi->decode_get_frame(r.ctx,&frame.value);
            if(rc==MPP_ERR_TIMEOUT || (rc==MPP_OK && !frame.value)) {
                if(ms(CLOCK_MONOTONIC)-begin>10000.)throw std::runtime_error("MPP frame receive timed out");
                continue;
            }
            check(rc,"decode_get_frame");
            if(mpp_frame_get_info_change(frame.value)) {
                if(mpp_frame_get_width(frame.value)!=1280 || mpp_frame_get_height(frame.value)!=720)
                    throw std::runtime_error("MPP resolution changed");
                size_t size=mpp_frame_get_buf_size(frame.value);
                if(!r.group)check(mpp_buffer_group_get_internal(&r.group,static_cast<MppBufferType>(MPP_BUFFER_TYPE_DRM|MPP_BUFFER_FLAGS_CACHABLE)),"create cached MPP pool");
                check(mpp_buffer_group_limit_config(r.group,size,24),"limit MPP pool");
                check(r.mpi->control(r.ctx,MPP_DEC_SET_EXT_BUF_GROUP,r.group),"bind MPP buffer pool");
                check(r.mpi->control(r.ctx,MPP_DEC_SET_INFO_CHANGE_READY,nullptr),"accept MPP information change");
                r.info_changes++;mpp_frame_deinit(&frame.value);continue;
            }
            if(mpp_frame_get_errinfo(frame.value) || mpp_frame_get_discard(frame.value))throw std::runtime_error("MPP returned an erroneous/discarded frame");
            auto buffer=mpp_frame_get_buffer(frame.value);
            if(mpp_frame_get_eos(frame.value))r.eos_seen=true;
            if(!buffer) {
                if(r.eos_seen)return 0;
                throw std::runtime_error("MPP returned empty non-EOS frame");
            }
            break;
        }
        timing->wall[0]=ms(CLOCK_MONOTONIC)-begin;timing->cpu[0]=ms(CLOCK_THREAD_CPUTIME_ID)-cpu;
        auto f=frame.value;auto format=mpp_frame_get_fmt(f);
        int hs=mpp_frame_get_hor_stride(f),vs=mpp_frame_get_ver_stride(f);
        if(format!=MPP_FMT_YUV420SP || mpp_frame_get_width(f)!=1280 || mpp_frame_get_height(f)!=720 ||
           hs<1280 || vs<720 || mpp_frame_get_offset_x(f) || mpp_frame_get_offset_y(f))
            throw std::runtime_error("Unsupported MPP format, stride, crop or geometry");
        int64_t pts=mpp_frame_get_pts(f);
        __int128 num=(__int128(pts)-r.start_pts)*r.timebase.num*r.rate.num;
        __int128 den=__int128(r.timebase.den)*r.rate.den;
        if(num<0 || num%den || num/den!=r.output_index)throw std::runtime_error("MPP PTS/display frame order mismatch");
        timing->pts=pts;r.output_index++;receive_lock.unlock();
        auto buffer=mpp_frame_get_buffer(f);size_t needed=size_t(hs)*vs*3/2;
        if(mpp_buffer_get_size(buffer)<needed)throw std::runtime_error("MPP buffer smaller than reported strides");
        begin=ms(CLOCK_MONOTONIC);cpu=ms(CLOCK_THREAD_CPUTIME_ID);
        check(mpp_buffer_sync_ro_begin(buffer),"begin CPU read synchronization");
        timing->wall[1]=ms(CLOCK_MONOTONIC)-begin;timing->cpu[1]=ms(CLOCK_THREAD_CPUTIME_ID)-cpu;
        try {
            auto y=static_cast<uint8_t*>(mpp_buffer_get_ptr(buffer));if(!y)throw std::runtime_error("MPP buffer map failed");
            begin=ms(CLOCK_MONOTONIC);cpu=ms(CLOCK_THREAD_CPUTIME_ID);
            const uint8_t* uv=y+size_t(hs)*vs;
            if(fp16) {
                // Keep the reference unscaled I420->BGR converter, but consume 24
                // BGR rows while hot in cache and write directly to RKNN FP16 memory.
                // The display variant also retains the full BGR image for later drawing.
                double start=ms(CLOCK_MONOTONIC),start_cpu=ms(CLOCK_THREAD_CPUTIME_ID);
                if(clear_padding){
                    std::memset(fp16,0,size_t(140)*640*3*2);
                    std::memset(fp16+size_t(500)*640*3,0,size_t(140)*640*3*2);
                }
                timing->prepare_wall+=ms(CLOCK_MONOTONIC)-start;timing->prepare_cpu+=ms(CLOCK_THREAD_CPUTIME_ID)-start_cpu;
                for(int row=0;row<720;row+=24) {
                    start=ms(CLOCK_MONOTONIC);start_cpu=ms(CLOCK_THREAD_CPUTIME_ID);
                    for(int k=0;k<12;k++)for(int x=0;x<640;x+=16) {
                        auto values=vld2q_u8(uv+size_t(row/2+k)*hs+x*2);
                        vst1q_u8(w.u.data()+k*640+x,values.val[0]);vst1q_u8(w.v.data()+k*640+x,values.val[1]);
                    }
                    timing->wall[2]+=ms(CLOCK_MONOTONIC)-start;timing->cpu[2]+=ms(CLOCK_THREAD_CPUTIME_ID)-start_cpu;
                    start=ms(CLOCK_MONOTONIC);start_cpu=ms(CLOCK_THREAD_CPUTIME_ID);
                    w.tiled_scale=r.p_sws_getCachedContext(w.tiled_scale,1280,24,AV_PIX_FMT_YUV420P,1280,24,AV_PIX_FMT_BGR24,SWS_BICUBIC,nullptr,nullptr,nullptr);
                    if(!w.tiled_scale)throw std::runtime_error("Tiled swscale initialization failed");
                    const uint8_t* src[4]={y+size_t(row)*hs,w.u.data(),w.v.data(),nullptr};int strides[4]={hs,640,640,0};
                    uint8_t* bgr=target?target+size_t(row)*3840:w.tile.data();
                    uint8_t* dst[4]={bgr,nullptr,nullptr,nullptr};int dst_strides[4]={3840,0,0,0};
                    if(r.p_sws_scale(w.tiled_scale,src,strides,0,24,dst,dst_strides)!=24)throw std::runtime_error("Tiled color conversion incomplete");
                    timing->wall[3]+=ms(CLOCK_MONOTONIC)-start;timing->cpu[3]+=ms(CLOCK_THREAD_CPUTIME_ID)-start_cpu;
                    start=ms(CLOCK_MONOTONIC);start_cpu=ms(CLOCK_THREAD_CPUTIME_ID);
                    if(cp_rows(bgr,3840,fp16,w.lut.data(),12,140+row/2))throw std::runtime_error("Tiled FP16 preparation failed");
                    timing->prepare_wall+=ms(CLOCK_MONOTONIC)-start;timing->prepare_cpu+=ms(CLOCK_THREAD_CPUTIME_ID)-start_cpu;
                }
            } else {
            {

                int first=0;
                int last=720;
                int height=last-first;
                begin=ms(CLOCK_MONOTONIC);cpu=ms(CLOCK_THREAD_CPUTIME_ID);
                for(int row=0;row<height/2;row++)for(int x=0;x<640;x+=16) {
                    auto values=vld2q_u8(uv+size_t(row+first/2)*hs+x*2);
                    vst1q_u8(w.u.data()+row*640+x,values.val[0]);vst1q_u8(w.v.data()+row*640+x,values.val[1]);
                }
                timing->wall[2]+=ms(CLOCK_MONOTONIC)-begin;timing->cpu[2]+=ms(CLOCK_THREAD_CPUTIME_ID)-cpu;
                begin=ms(CLOCK_MONOTONIC);cpu=ms(CLOCK_THREAD_CPUTIME_ID);
                SwsContext*& context=w.scale;
                context=r.p_sws_getCachedContext(context,1280,height,AV_PIX_FMT_YUV420P,1280,height,AV_PIX_FMT_BGR24,
                    SWS_BICUBIC,nullptr,nullptr,nullptr);
                if(!context)throw std::runtime_error("sws_getCachedContext failed");
                const uint8_t* src[4]={y+size_t(first)*hs,w.u.data(),w.v.data(),nullptr};int strides[4]={hs,640,640,0};
                uint8_t* dst[4]={target,nullptr,nullptr,nullptr};int out_strides[4]={3840,0,0,0};
                if(r.p_sws_scale(context,src,strides,0,height,dst,out_strides)!=height)throw std::runtime_error("Incomplete BGR conversion");
                timing->wall[3]+=ms(CLOCK_MONOTONIC)-begin;timing->cpu[3]+=ms(CLOCK_THREAD_CPUTIME_ID)-cpu;
            }
            }
        }catch(...){mpp_buffer_sync_ro_end(buffer);throw;}
        begin=ms(CLOCK_MONOTONIC);cpu=ms(CLOCK_THREAD_CPUTIME_ID);
        check(mpp_buffer_sync_ro_end(buffer),"end CPU read synchronization");mpp_frame_deinit(&frame.value);
        timing->wall[4]=ms(CLOCK_MONOTONIC)-begin;timing->cpu[4]=ms(CLOCK_THREAD_CPUTIME_ID)-cpu;
        r.frames++;r.condition.notify_all();return 1;
    }catch(const std::exception& e){error(err,cap,e.what());return -1;}
}

int mp_read(void* handle,uint8_t* target,size_t bytes,mp_timing* timing,char* err,unsigned cap) {
    auto& r=*static_cast<Reader*>(handle);return read_impl(handle,target,bytes,timing,err,cap,r.work);
}
int mp_read_fused(void* handle,uint8_t* bgr,size_t bytes,uint16_t* fp16,int clear_padding,mp_timing* timing,char* err,unsigned cap) {
    if(!fp16){error(err,cap,"Missing FP16 destination");return -1;}
    auto& r=*static_cast<Reader*>(handle);return read_impl(handle,bgr,bytes,timing,err,cap,r.work,fp16,clear_padding!=0);
}

const char* mp_stats(void* handle) {
    auto& r=*static_cast<Reader*>(handle);std::ostringstream out;
    out<<"{\"accepted_packets\":"<<r.accepted<<",\"hardware_frames\":"<<r.frames<<",\"packet_retries\":"<<r.retries
       <<",\"information_changes\":"<<r.info_changes<<",\"put_wall_ms\":"<<r.put_wall_ns.load()/1e6
       <<",\"put_cpu_ms\":"<<r.put_cpu_ns.load()/1e6<<",\"eos_received\":"<<(r.eos_seen?"true":"false")
       <<",\"sender_tid\":"<<r.sender_tid<<",\"compressed_packet_bound\":8,\"frame_pool_bound\":24}";
    r.stats=out.str();return r.stats.c_str();
}
int mp_sender_tid(void* handle){return static_cast<Reader*>(handle)->sender_tid;}
void mp_cancel(void* handle){static_cast<Reader*>(handle)->cancel();}
void mp_close(void* handle){delete static_cast<Reader*>(handle);}
}
