// Owned-runtime regression: resource load/unload only; never starts the game or creates a display.
#define NOMINMAX
#include <Windows.h>
#include <psapi.h>
#include <iostream>
#include <cassert>
#include <filesystem>
#include <fstream>
#include <vector>
#include <string>
#include <algorithm>
#include <cstdint>
template<class T>T symbol(HMODULE mod,const char* name) { auto fn=GetProcAddress(mod,name);if(!fn){std::cerr<<"missing "<<name<<"\n";ExitProcess(2);}return reinterpret_cast<T>(fn); }
int main(int argc,char** argv) {
 SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX);SetPriorityClass(GetCurrentProcess(),IDLE_PRIORITY_CLASS);
 std::cout<<std::unitbuf;std::cerr<<std::unitbuf;
 SetUnhandledExceptionFilter([](EXCEPTION_POINTERS* e)->LONG {std::cerr<<"fault "<<std::hex<<e->ContextRecord->Eip<<" address "<<e->ExceptionRecord->ExceptionInformation[1]<<"\n";ExitProcess(3);});
 assert(argc>=3);
 const auto directory=std::filesystem::absolute(argv[1]);SetDllDirectoryW(directory.c_str());
 auto core=LoadLibraryW((directory/L"libIGCore.dll").c_str());if(!core){std::cerr<<"load core error "<<GetLastError()<<"\n";return 2;}
 auto ark=symbol<void**>(core,"?ArkCore@Core@Gap@@3PAVigArkCore@12@A");
 std::cout<<"core "<<core<<" ark "<<*ark<<"\n";
 if(!*ark) { *ark=VirtualAlloc(nullptr,0x1000,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);symbol<void*(__thiscall*)(void*)>(core,"??0igArkCore@Core@Gap@@QAE@XZ")(*ark);std::cout<<"constructed ark\n"; }
 symbol<void(__thiscall*)(void*)>(core,"?initBootstrap@igArkCore@Core@Gap@@QAEXXZ")(*ark);std::cout<<"bootstrap\n";
 symbol<void(__thiscall*)(void*)>(core,"?initCore@igArkCore@Core@Gap@@QAEXXZ")(*ark);std::cout<<"core init\n";
 for(const auto name:{L"libIGMath.dll",L"libIGSg.dll",L"libIGAttrs.dll"}) {auto m=LoadLibraryW((directory/name).c_str());std::cout<<"load "<<m<<"\n";}
 for(const auto name:{L"libIGMath.dll",L"libIGSg.dll",L"libIGGfx.dll"}) { auto m=LoadLibraryW((directory/name).c_str()); const char* ns=name==std::wstring(L"libIGMath.dll") ? "?igArkRegisterForIGBFiles@Math@Gap@@YAXXZ" : name==std::wstring(L"libIGSg.dll") ? "?igArkRegisterForIGBFiles@Sg@Gap@@YAXXZ" : "?igArkRegisterForIGBFiles@Gfx@Gap@@YAXXZ";symbol<void(__cdecl*)()>(m,ns)();std::cout<<"registered "<<ns<<"\n"; }
 auto res=symbol<void**>(core,"?igIGBResource@Core@Gap@@3PAVigResource@12@A");std::cout<<"resource "<<*res<<"\n";

 assert(*res);
 auto load=symbol<void*(__thiscall*)(void*,const char*)>(core,"?load@igResource@Core@Gap@@QAEPAVigDirectory@23@QBD@Z");
 auto unload=symbol<void(__thiscall*)(void*,const char*)>(core,"?unload@igResource@Core@Gap@@QAEXQBD@Z");
 auto infos=symbol<void*(__thiscall*)(void*)>(core,"?getInfoList@igDirectory@Core@Gap@@QBEPBVigInfoList@23@XZ");
 std::vector<std::string> files;std::ifstream list(argv[2]);std::string file;
 while(std::getline(list,file)) { if(!file.empty() && file.back()=='\r')file.pop_back();if(!file.empty())files.push_back(file); }
 assert(!files.empty());const int cycles=argc>3 ? std::stoi(argv[3]) : 8;
 const int warmup=argc>4 ? std::stoi(argv[4]) : 2;const bool expect_leak=argc>5 && std::stoi(argv[5]);
 assert(cycles>=2 && warmup>=0); // One sample cannot establish a memory range.
 SIZE_T low=SIZE_MAX,high=0;DWORD low_handles=MAXDWORD,high_handles=0;
 for(int i=0;i<cycles+warmup;++i) {
   // Hold the entire screen's resources until close, as a live menu does.
   for(const auto& name:files) {
     auto value=load(*res,name.c_str());auto info=value ? infos(value) : nullptr;
     if(!info || !reinterpret_cast<unsigned*>(info)[2]) { std::cerr<<"asset did not load: "<<name<<"\n";return 4; }
   }
   for(auto it=files.rbegin();it!=files.rend();++it)unload(*res,it->c_str());
   PROCESS_MEMORY_COUNTERS_EX pm{};pm.cb=sizeof(pm);assert(GetProcessMemoryInfo(GetCurrentProcess(),reinterpret_cast<PROCESS_MEMORY_COUNTERS*>(&pm),sizeof(pm)));
   DWORD handles=0;assert(GetProcessHandleCount(GetCurrentProcess(),&handles));
   std::cout<<"sample "<<i<<" private "<<pm.PrivateUsage<<" rss "<<pm.WorkingSetSize<<" handles "<<handles<<" models "<<files.size()<<"\n";
   if(i>=warmup) { low=std::min(low,pm.PrivateUsage);high=std::max(high,pm.PrivateUsage);low_handles=std::min(low_handles,handles);high_handles=std::max(high_handles,handles); }
 }
 const auto growth=high-low;std::cout<<"range private "<<growth<<" handles "<<(high_handles-low_handles)<<"\n";
 if(expect_leak) { assert(growth>1024*1024);std::cout<<"EXPECTED LEAK reproduced\n"; }
 else { assert(growth<=256*1024 && low_handles==high_handles);std::cout<<"PASS flat memory and handles after warmup\n"; }
 return 0;
}
