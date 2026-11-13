// SPDX-License-Identifier: AGPL-3.0-only
// Three input buffers with independent MPP packet draining.
extern "C" {
#include <rk_mpi.h>
#include <rk_venc_cfg.h>
#include <mpp_buffer.h>
#include <mpp_frame.h>
#include <mpp_meta.h>
#include <mpp_packet.h>
}
#include "encoder_pixels.h"
#include <atomic>
#include <array>
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <cstring>
#include <deque>
#include <iomanip>
#include <map>
#include <memory>
#include <mutex>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

namespace {
using Clock=std::chrono::steady_clock;
double now(){return std::chrono::duration<double,std::milli>(Clock::now().time_since_epoch()).count();}
void check(int rc,const char* where){if(rc)throw std::runtime_error(std::string(where)+": "+std::to_string(rc));}
void error(char* out,unsigned cap,const char* value){if(out&&cap)std::snprintf(out,cap,"%s",value);}
struct Slot {
    MppBuffer buffer=nullptr;MppFrame frame=nullptr;
    int64_t sequence=-1;bool returned=false,eoi=false;double submitted_at=0;
};
struct Encoder {
    MppCtx ctx=nullptr;MppApi* api=nullptr;MppEncCfg cfg=nullptr;FILE* file=nullptr;
    std::array<Slot,3> slots;std::deque<int> free;std::map<MppFrame,int> outstanding;
    std::mutex mutex,writer;std::condition_variable condition;std::thread receiver;
    std::atomic<bool> abort{false};std::string failure,stats;
    int width=0,height=0,hs=0,vs=0;bool finished=false,eos=false;
    int64_t frames=0,submitted=0,completed=0,packets=0,bytes=0,partitions=0;
    double wait_ms=0,convert_ms=0,submit_ms=0,packet_ms=0,finish_ms=0;
    std::atomic<int> delay_ms{0},fail_after{-1};std::vector<std::pair<int64_t,double>> events;
    void fail(const std::string& message){std::lock_guard<std::mutex> lock(mutex);if(failure.empty())failure=message;abort=true;condition.notify_all();}
    void valid(){if(!failure.empty())throw std::runtime_error(failure);}
    void recycle_locked(int index){
        auto& s=slots[index];
        if(!s.returned||!s.eoi)return;
        outstanding.erase(s.frame);mpp_frame_deinit(&s.frame);completed++;
        events.emplace_back(s.sequence,now()/1000.);s.sequence=-1;s.returned=s.eoi=false;
        free.push_back(index);condition.notify_all();
    }
    void receive(){
        try{
            while(!abort){
                MppPacket p=nullptr;double start=now();int rc=api->encode_get_packet(ctx,&p);
                if(rc==MPP_ERR_TIMEOUT||(!rc&&!p))continue;
                check(rc,"encode_get_packet");
                try{
                    if(delay_ms)std::this_thread::sleep_for(std::chrono::milliseconds(delay_ms));
                    size_t size=mpp_packet_get_length(p);bool end=mpp_packet_get_eos(p)!=0;
                    bool split=mpp_packet_is_partition(p)!=0;
                    bool eoi=!split||mpp_packet_is_eoi(p)!=0;
                    int64_t pts=mpp_packet_get_pts(p);MppFrame returned=nullptr;
                    if(mpp_packet_has_meta(p))mpp_meta_get_frame(mpp_packet_get_meta(p),KEY_INPUT_FRAME,&returned);
                    if(size&&std::fwrite(mpp_packet_get_pos(p),1,size,file)!=size)throw std::runtime_error("Compressed output write failed");
                    {
                        std::lock_guard<std::mutex> lock(mutex);
                        if(size){bytes+=size;packets++;}if(split)partitions++;
                        int returned_index=-2;
                        if(returned){
                            auto found=outstanding.find(returned);
                            if(found==outstanding.end())throw std::runtime_error("Unknown MPP returned input frame");
                            returned_index=found->second;
                            if(returned_index<0){outstanding.erase(found);mpp_frame_deinit(&returned);}
                            else {slots[returned_index].returned=true;if(pts<0)pts=slots[returned_index].sequence;}
                        }
                        if(eoi&&size){for(auto& s:slots)if(s.frame&&s.sequence==pts)s.eoi=true;}
                        // Some runtimes attach the input to the final packet without a valid packet PTS.
                        if(eoi&&returned_index>=0)slots[returned_index].eoi=true;
                        for(int i=0;i<3;i++)recycle_locked(i);
                        packet_ms+=now()-start;
                        if(fail_after>=0&&packets>=fail_after)throw std::runtime_error("injected packet failure");
                        if(end){eos=true;condition.notify_all();}
                    }
                    mpp_packet_deinit(&p);if(end)return;
                }catch(...){if(p)mpp_packet_deinit(&p);throw;}
            }
        }catch(const std::exception& e){fail(e.what());}
    }
    void send(MppFrame frame){
        double start=now();
        while(true){
            {std::lock_guard<std::mutex> lock(mutex);valid();}
            int rc=api->encode_put_frame(ctx,frame);
            if(!rc)break;
            if(now()-start>10000)throw std::runtime_error("MPP frame submission timeout: "+std::to_string(rc));
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
        }
        submit_ms+=now()-start;
    }
    void write(const uint8_t* bgr,int stride){
        std::lock_guard<std::mutex> writing(writer);int index;
        double start=now();
        {
            std::unique_lock<std::mutex> lock(mutex);valid();if(finished)throw std::runtime_error("Encoder already closed");
            if(!condition.wait_for(lock,std::chrono::seconds(10),[&]{return !free.empty()||!failure.empty();}))throw std::runtime_error("Encoder input pool timeout");
            valid();index=free.front();free.pop_front();
        }
        wait_ms+=now()-start;auto& s=slots[index];start=now();
        check(mpp_buffer_sync_begin(s.buffer),"NV12 CPU begin");
        auto data=static_cast<uint8_t*>(mpp_buffer_get_ptr(s.buffer));
        output_pixels::convert(bgr,stride,data,data+size_t(hs)*vs,width,height,hs);
        check(mpp_buffer_sync_end(s.buffer),"NV12 CPU end");
        convert_ms+=now()-start;
        MppFrame f=nullptr;check(mpp_frame_init(&f),"frame init");
        mpp_frame_set_width(f,width);mpp_frame_set_height(f,height);mpp_frame_set_hor_stride(f,hs);mpp_frame_set_ver_stride(f,vs);
        mpp_frame_set_fmt(f,MPP_FMT_YUV420SP);mpp_frame_set_buffer(f,s.buffer);mpp_frame_set_pts(f,frames);
        try{
            std::lock_guard<std::mutex> lock(mutex);valid();s.frame=f;s.sequence=frames;s.returned=s.eoi=false;s.submitted_at=now();outstanding[f]=index;
        }catch(...){mpp_frame_deinit(&f);throw;}
        send(f);frames++;submitted++;
    }
    void finish(){
        std::lock_guard<std::mutex> writing(writer);if(finished)return;
        double start=now();
        {std::lock_guard<std::mutex> lock(mutex);valid();}
        if(frames){
            MppFrame f=nullptr;check(mpp_frame_init(&f),"EOS frame init");
            mpp_frame_set_width(f,width);mpp_frame_set_height(f,height);mpp_frame_set_hor_stride(f,hs);mpp_frame_set_ver_stride(f,vs);
            mpp_frame_set_fmt(f,MPP_FMT_YUV420SP);mpp_frame_set_pts(f,frames);mpp_frame_set_eos(f,1);
            {std::lock_guard<std::mutex> lock(mutex);outstanding[f]=-1;}
            send(f);
            std::unique_lock<std::mutex> lock(mutex);
            if(!condition.wait_for(lock,std::chrono::seconds(20),[&]{return eos||!failure.empty();}))throw std::runtime_error("Encoder EOS drain timeout");
            valid();if(completed!=frames)throw std::runtime_error("MPP did not return every complete input frame");
        }else abort=true;
        if(receiver.joinable())receiver.join();
        if(std::fflush(file))throw std::runtime_error("Compressed output flush failed");
        finished=true;finish_ms=now()-start;
    }
    ~Encoder(){
        abort=true;condition.notify_all();if(receiver.joinable())receiver.join();
        if(ctx){api->reset(ctx);mpp_destroy(ctx);}
        for(auto& entry:outstanding){MppFrame f=entry.first;mpp_frame_deinit(&f);}
        for(auto& s:slots)if(s.buffer)mpp_buffer_put(s.buffer);
        if(cfg)mpp_enc_cfg_deinit(cfg);if(file)std::fclose(file);
    }
};
}
extern "C" {
void* out_open(const char* path,int width,int height,int fps_num,int fps_den,int bitrate,char* err,unsigned cap){
    try{
        if(width%16||height%2||width<16||height<2||fps_num<1||fps_den<1)throw std::runtime_error("Invalid encoding geometry/rate");
        auto e=std::make_unique<Encoder>();e->width=width;e->height=height;e->hs=width;e->vs=(height+15)/16*16;
        e->file=std::fopen(path,"wb");if(!e->file)throw std::runtime_error("Cannot create compressed output");
        check(mpp_create(&e->ctx,&e->api),"mpp_create");RK_S64 timeout=100;
        check(e->api->control(e->ctx,MPP_SET_OUTPUT_TIMEOUT,&timeout),"output timeout");timeout=0;
        check(e->api->control(e->ctx,MPP_SET_INPUT_TIMEOUT,&timeout),"input timeout");
        check(mpp_init(e->ctx,MPP_CTX_ENC,MPP_VIDEO_CodingAVC),"mpp_init");
        check(mpp_enc_cfg_init(&e->cfg),"cfg init");check(e->api->control(e->ctx,MPP_ENC_GET_CFG,e->cfg),"get cfg");
        auto set=[&](const char* key,int value){check(mpp_enc_cfg_set_s32(e->cfg,key,value),key);};
        set("prep:width",width);set("prep:height",height);set("prep:hor_stride",e->hs);set("prep:ver_stride",e->vs);set("prep:format",MPP_FMT_YUV420SP);
        set("rc:mode",MPP_ENC_RC_MODE_CBR);set("rc:fps_in_flex",0);set("rc:fps_in_num",fps_num);set("rc:fps_in_denorm",fps_den);
        set("rc:fps_out_flex",0);set("rc:fps_out_num",fps_num);set("rc:fps_out_denorm",fps_den);set("rc:gop",fps_num/fps_den);
        set("rc:bps_target",bitrate);set("rc:bps_max",bitrate*17/16);set("rc:bps_min",bitrate*15/16);
        set("rc:qp_init",26);set("rc:qp_max",48);set("rc:qp_min",10);set("rc:qp_max_i",48);set("rc:qp_min_i",10);
        set("h264:profile",100);set("h264:level",40);set("h264:cabac_en",1);set("h264:trans8x8",1);
        check(e->api->control(e->ctx,MPP_ENC_SET_CFG,e->cfg),"set cfg");
        MppEncHeaderMode mode=MPP_ENC_HEADER_MODE_EACH_IDR;check(e->api->control(e->ctx,MPP_ENC_SET_HEADER_MODE,&mode),"header mode");
        for(int i=0;i<3;i++){
            auto& s=e->slots[i];size_t size=size_t(e->hs)*e->vs*3/2;
            check(mpp_buffer_get(nullptr,&s.buffer,size),"NV12 input");
            check(mpp_buffer_sync_begin(s.buffer),"init NV12");auto data=static_cast<uint8_t*>(mpp_buffer_get_ptr(s.buffer));
            std::memset(data,16,size_t(e->hs)*e->vs);std::memset(data+size_t(e->hs)*e->vs,128,size/3);check(mpp_buffer_sync_end(s.buffer),"init NV12 end");
            e->free.push_back(i);
        }
        e->receiver=std::thread([p=e.get()]{p->receive();});return e.release();
    }catch(const std::exception& e){error(err,cap,e.what());return nullptr;}
}
int out_write(void* h,const uint8_t* bgr,int stride,char* err,unsigned cap){
    auto& e=*static_cast<Encoder*>(h);try{e.write(bgr,stride);return 0;}catch(const std::exception& x){e.fail(x.what());error(err,cap,x.what());return -1;}
}
int out_finish(void* h,char* err,unsigned cap){auto& e=*static_cast<Encoder*>(h);try{e.finish();return 0;}catch(const std::exception& x){e.fail(x.what());error(err,cap,x.what());return -1;}}
void out_cancel(void* h){static_cast<Encoder*>(h)->fail("Encoding cancelled");}
void out_close(void* h){delete static_cast<Encoder*>(h);}
int out_test(void* h,int delay,int failure,int split,char* err,unsigned cap){
    try{auto& e=*static_cast<Encoder*>(h);e.delay_ms=delay;e.fail_after=failure;if(split){
        check(mpp_enc_cfg_set_s32(e.cfg,"split:mode",1),"split mode");check(mpp_enc_cfg_set_s32(e.cfg,"split:arg",split),"split bytes");
        check(mpp_enc_cfg_set_s32(e.cfg,"split:out",1),"split output");check(e.api->control(e.ctx,MPP_ENC_SET_CFG,e.cfg),"set partition cfg");
    }return 0;}catch(const std::exception& x){error(err,cap,x.what());return -1;}
}
const char* out_stats(void* h){
    auto& e=*static_cast<Encoder*>(h);std::lock_guard<std::mutex> lock(e.mutex);std::ostringstream s;
    s<<"{\"frames\":"<<e.frames<<",\"submitted\":"<<e.submitted<<",\"completed\":"<<e.completed<<",\"packets\":"<<e.packets<<",\"partition_packets\":"<<e.partitions
     <<",\"encoded_bytes\":"<<e.bytes<<",\"eos_received\":"<<(e.eos?"true":"false")<<",\"input_buffers\":3,\"free_buffers\":"<<e.free.size()
     <<",\"buffer_wait_ms\":"<<e.wait_ms<<",\"convert_wall_ms\":"<<e.convert_ms<<",\"submit_wall_ms\":"<<e.submit_ms<<",\"packet_wall_ms\":"<<e.packet_ms<<",\"finish_ms\":"<<e.finish_ms
     <<",\"width\":"<<e.width<<",\"height\":"<<e.height<<",\"horizontal_stride\":"<<e.hs<<",\"vertical_stride\":"<<e.vs<<",\"completion_events\":[";
    bool first=true;for(auto& event:e.events){if(!first)s<<",";first=false;s<<"["<<event.first<<","<<std::fixed<<std::setprecision(9)<<event.second<<"]";}
    s<<"]}";e.stats=s.str();return e.stats.c_str();
}
}
