# SPDX-License-Identifier: AGPL-3.0-only
"""Matched-window /proc CPU ledger; application threads park until end snapshot."""
import os
from pathlib import Path
import threading
import time

_enabled=False
_roles={}
_lock=threading.Lock()


def enable():
    global _enabled
    _enabled=True


def snapshot():
    result={}
    ticks=os.sysconf('SC_CLK_TCK')
    try: sched_enabled=Path('/proc/sys/kernel/sched_schedstats').read_text().strip()=='1'
    except OSError:sched_enabled=False
    for folder in Path('/proc/self/task').iterdir():
        try:
            raw=(folder/'stat').read_text();fields=raw[raw.rfind(')')+2:].split()
            identity=(int(folder.name),int(fields[19]))
            row={'tid':identity[0],'start_ticks':identity[1],'name':raw[raw.find('(')+1:raw.rfind(')')],
                 'user_ms':int(fields[11])*1000/ticks,'system_ms':int(fields[12])*1000/ticks,
                 'runqueue_wait_ms':None,'voluntary_switches':0,'involuntary_switches':0}
            if sched_enabled:
                row['runqueue_wait_ms']=int((folder/'schedstat').read_text().split()[1])/1e6
            for line in (folder/'status').read_text().splitlines():
                if line.startswith('voluntary_ctxt_switches:'):row['voluntary_switches']=int(line.split()[-1])
                elif line.startswith('nonvoluntary_ctxt_switches:'):row['involuntary_switches']=int(line.split()[-1])
            result[identity]=row
        except (OSError,IndexError,ValueError):continue
    return result


def mark_current(role):
    if not _enabled:return
    tid=threading.get_native_id()
    rows=snapshot()
    with _lock:
        for identity in rows:
            if identity[0]==tid:_roles[identity]={'role':role,'evidence':'registered application thread'}


def mark_native(tid,role,evidence):
    if not _enabled:return
    rows=snapshot()
    with _lock:
        for identity in rows:
            if identity[0]==tid:_roles[identity]={'role':role,'evidence':evidence}


def before_creation():return snapshot() if _enabled else None


def after_creation(before,role,evidence):
    if before is None:return
    after=snapshot()
    with _lock:
        for identity in after.keys()-before.keys():
            _roles.setdefault(identity,{'role':role,'evidence':evidence})


class Phase:
    def __init__(self):
        enable()
        self.go=threading.Event();self.release=threading.Event();self.cancelled=threading.Event()
        self.condition=threading.Condition();self.ready=0;self.finished=0
        self.initial=None

    def wrap(self,role,function):
        def run():
            mark_current(role)
            with self.condition:self.ready+=1;self.condition.notify_all()
            self.go.wait()
            try:
                if not self.cancelled.is_set():function()
            finally:
                with self.condition:self.finished+=1;self.condition.notify_all()
                self.release.wait()
        return run

    def start(self,count,release=True):
        self.count=count
        with self.condition:
            if not self.condition.wait_for(lambda:self.ready==count,timeout=30):
                raise RuntimeError('CPU ledger start barrier timed out')
        mark_current('main_output')
        self.initial=snapshot()
        cpu=time.process_time();wall=time.perf_counter()
        if release:self.go.set()
        return wall,cpu

    def end(self,cpu_started,frames):
        with self.condition:
            if not self.condition.wait_for(lambda:self.finished==self.count,timeout=30):
                raise RuntimeError('CPU ledger finish barrier timed out')
        final=snapshot();cpu_ms=(time.process_time()-cpu_started)*1000;ended=time.perf_counter()
        rows=[]
        for identity,row in final.items():
            old=self.initial.get(identity,{})
            delta={key:row[key]-old.get(key,0) for key in ('user_ms','system_ms','voluntary_switches','involuntary_switches')}
            wait=row['runqueue_wait_ms']
            delta['runqueue_wait_ms']=None if wait is None else wait-(old.get('runqueue_wait_ms') or 0)
            with _lock:role=_roles.get(identity,{'role':'unidentified','evidence':'no registered creation boundary'})
            rows.append({**row,**delta,**role,'cpu_ms':delta['user_ms']+delta['system_ms']})
        roles={}
        for row in rows:
            group=roles.setdefault(row['role'],{'cpu_ms':0.,'user_ms':0.,'system_ms':0.,'threads':0,
                'runqueue_wait_ms':None,'voluntary_switches':0,'involuntary_switches':0})
            group['threads']+=1
            for key in ('cpu_ms','user_ms','system_ms','voluntary_switches','involuntary_switches'):group[key]+=row[key]
            if row['runqueue_wait_ms'] is not None:group['runqueue_wait_ms']=(group['runqueue_wait_ms'] or 0)+row['runqueue_wait_ms']
        thread_cpu=sum(r['cpu_ms'] for r in rows)
        for group in roles.values():group['cpu_ms_per_image']=group['cpu_ms']/frames if frames else None
        error=abs(thread_cpu-cpu_ms)/cpu_ms if cpu_ms else 1.
        result={'passed':error<=.03,'closure_error_fraction':error,'process_cpu_ms':cpu_ms,
                'thread_cpu_ms':thread_cpu,'roles':roles,'threads':rows,
                'vanished_threads':[list(k) for k in self.initial.keys()-final.keys()],
                'clock_ticks_per_second':os.sysconf('SC_CLK_TCK'),
                'note':'thread totals and per-stage scopes are separate views; do not add them together'}
        self.release.set()
        return result,cpu_ms,ended

    def abort(self):
        self.cancelled.set();self.go.set();self.release.set()
