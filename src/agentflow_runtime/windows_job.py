"""Windows Job Object: no breakaway allowed; gate prevents launching before assignment."""
import ctypes as C
from ctypes import wintypes as W
import os
import time

class BasicLimit(C.Structure):
    _fields_=[('PerProcessUserTimeLimit',C.c_longlong),('PerJobUserTimeLimit',C.c_longlong),('LimitFlags',W.DWORD),('MinimumWorkingSetSize',C.c_size_t),('MaximumWorkingSetSize',C.c_size_t),('ActiveProcessLimit',W.DWORD),('Affinity',C.c_size_t),('PriorityClass',W.DWORD),('SchedulingClass',W.DWORD)]
class IO(C.Structure):
    _fields_=[(n,C.c_ulonglong) for n in ('ReadOperationCount','WriteOperationCount','OtherOperationCount','ReadTransferCount','WriteTransferCount','OtherTransferCount')]
class ExtendedLimit(C.Structure):
    _fields_=[('BasicLimitInformation',BasicLimit),('IoInfo',IO),('ProcessMemoryLimit',C.c_size_t),('JobMemoryLimit',C.c_size_t),('PeakProcessMemoryUsed',C.c_size_t),('PeakJobMemoryUsed',C.c_size_t)]
class Accounting(C.Structure):
    _fields_=[(n,C.c_longlong) for n in ('TotalUserTime','TotalKernelTime','ThisPeriodTotalUserTime','ThisPeriodTotalKernelTime')]+[(n,W.DWORD) for n in ('TotalPageFaultCount','TotalProcesses','ActiveProcesses','TotalTerminatedProcesses')]

class WindowsJob:
    def __init__(self, pid):
        if os.name!='nt': raise OSError('Windows Job Objects require Windows')
        k=self.k=C.WinDLL('kernel32',use_last_error=True)
        for name,args,result in [
            ('CreateJobObjectW',[C.c_void_p,W.LPCWSTR],W.HANDLE),
            ('SetInformationJobObject',[W.HANDLE,C.c_int,C.c_void_p,W.DWORD],W.BOOL),
            ('OpenProcess',[W.DWORD,W.BOOL,W.DWORD],W.HANDLE),
            ('AssignProcessToJobObject',[W.HANDLE,W.HANDLE],W.BOOL),
            ('TerminateJobObject',[W.HANDLE,W.UINT],W.BOOL),
            ('QueryInformationJobObject',[W.HANDLE,C.c_int,C.c_void_p,W.DWORD,C.c_void_p],W.BOOL),
            ('CloseHandle',[W.HANDLE],W.BOOL)]:
            f=getattr(k,name);f.argtypes=args;f.restype=result
        self.handle=k.CreateJobObjectW(None,None)
        if not self.handle: raise C.WinError(C.get_last_error())
        try:
            config=ExtendedLimit();config.BasicLimitInformation.LimitFlags=0x2000 # KILL_ON_JOB_CLOSE
            self._check(k.SetInformationJobObject(self.handle,9,C.byref(config),C.sizeof(config)))
            process=k.OpenProcess(0x0100|0x0001,False,pid) # SET_QUOTA | TERMINATE
            self._check(process)
            try:self._check(k.AssignProcessToJobObject(self.handle,process))
            finally:k.CloseHandle(process)
        except BaseException:
            self.close();raise
    @staticmethod
    def _check(result):
        if not result:raise C.WinError(C.get_last_error())
    def stop(self):
        self._check(self.k.TerminateJobObject(self.handle,1))
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            a=Accounting();self._check(self.k.QueryInformationJobObject(self.handle,1,C.byref(a),C.sizeof(a),None))
            if not a.ActiveProcesses:return True
            time.sleep(.02)
        return False
    def close(self):
        if self.handle:self.k.CloseHandle(self.handle);self.handle=None
