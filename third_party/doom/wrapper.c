#define DOOM_IMPLEMENTATION
#include "PureDOOM.h"

#define EXPORT(name) __attribute__((export_name(name)))
#define IMPORT(name) __attribute__((import_module("env"), import_name(name)))

IMPORT("fs_open") extern int js_open(const char* name, const char* mode);
IMPORT("fs_close") extern void js_close(int handle);
IMPORT("fs_read") extern int js_read(int handle, void* buf, int count);
IMPORT("fs_write") extern int js_write(int handle, const void* buf, int count);
IMPORT("fs_seek") extern int js_seek(int handle, int offset, int origin);
IMPORT("fs_tell") extern int js_tell(int handle);
IMPORT("fs_eof") extern int js_eof(int handle);
IMPORT("host_print") extern void js_print(const char* text);
IMPORT("host_exit") extern void js_exit(int code);

extern unsigned char __heap_base;

typedef struct block
{
    unsigned size;
    unsigned used;
    struct block* next;
    unsigned pad;
} block_t;

static block_t* wd_head;
static block_t* wd_tail;
static unsigned heap_top;

static unsigned grow_to(unsigned wanted)
{
    unsigned have = (unsigned)__builtin_wasm_memory_size(0) * 65536u;
    if (wanted <= have)
        return 1;
    unsigned pages = (wanted - have + 65535u) / 65536u;
    return __builtin_wasm_memory_grow(0, pages) != (unsigned)-1;
}

static void* heap_alloc(int size)
{
    unsigned need = ((unsigned)size + 15u) & ~15u;
    block_t* it;
    for (it = wd_head; it; it = it->next)
    {
        if (!it->used && it->size >= need)
        {
            it->used = 1;
            return (void*)(it + 1);
        }
    }
    if (!heap_top)
        heap_top = ((unsigned)&__heap_base + 15u) & ~15u;
    if (!grow_to(heap_top + sizeof(block_t) + need))
        return 0;
    it = (block_t*)heap_top;
    it->size = need;
    it->used = 1;
    it->next = 0;
    heap_top += sizeof(block_t) + need;
    if (wd_tail)
        wd_tail->next = it;
    else
        wd_head = it;
    wd_tail = it;
    return (void*)(it + 1);
}

static void heap_release(void* ptr)
{
    if (ptr)
        ((block_t*)ptr - 1)->used = 0;
}

static void* host_malloc(int size)
{
    return heap_alloc(size);
}

static void host_free(void* ptr)
{
    heap_release(ptr);
}

static void* host_open(const char* name, const char* mode)
{
    return (void*)js_open(name, mode);
}

static void host_close(void* handle)
{
    js_close((int)handle);
}

static int host_read(void* handle, void* buf, int count)
{
    return js_read((int)handle, buf, count);
}

static int host_write(void* handle, const void* buf, int count)
{
    return js_write((int)handle, buf, count);
}

static int host_seek(void* handle, int offset, doom_seek_t origin)
{
    return js_seek((int)handle, offset, (int)origin);
}

static int host_tell(void* handle)
{
    return js_tell((int)handle);
}

static int host_eof(void* handle)
{
    return js_eof((int)handle);
}

static unsigned long long clock_tics;

static void host_time(int* sec, int* usec)
{
    unsigned long long tics = clock_tics;
    *sec = (int)(1000 + tics / 35);
    *usec = (int)(((tics % 35) * 1000000ull) / 35ull + 1ull);
}

static void host_exit(int code)
{
    js_exit(code);
    __builtin_trap();
}

static char home_dir[] = ".";

static char* host_getenv(const char* name)
{
    if (name[0] == 'H' && name[1] == 'O' && name[2] == 'M' && name[3] == 'E' && !name[4])
        return home_dir;
    return 0;
}

static char arguments[1024];
static char* argv_list[32];
static int argc_count;
static unsigned char sound_copy[2048];

EXPORT("args_ptr") char* wd_args_ptr(void)
{
    return arguments;
}

EXPORT("boot") void wd_boot(void)
{
    int i = 0;
    argc_count = 0;
    argv_list[argc_count++] = "doom";
    while (arguments[i] && argc_count < 31)
    {
        while (arguments[i] == ' ')
            arguments[i++] = 0;
        if (!arguments[i])
            break;
        argv_list[argc_count++] = &arguments[i];
        while (arguments[i] && arguments[i] != ' ')
            i++;
    }
    argv_list[argc_count] = 0;
    doom_set_malloc(host_malloc, host_free);
    doom_set_file_io(host_open, host_close, host_read, host_write, host_seek, host_tell, host_eof);
    doom_set_gettime(host_time);
    doom_set_exit(host_exit);
    doom_set_getenv(host_getenv);
    doom_set_print((doom_print_fn)js_print);
    doom_set_default_int("key_up", DOOM_KEY_UP_ARROW);
    doom_set_default_int("key_down", DOOM_KEY_DOWN_ARROW);
    doom_set_default_int("key_left", DOOM_KEY_LEFT_ARROW);
    doom_set_default_int("key_right", DOOM_KEY_RIGHT_ARROW);
    doom_set_default_int("mouse_move", 0);
    doom_init(argc_count, argv_list, 0);
}

EXPORT("step") void wd_step(void)
{
    clock_tics++;
    doom_force_update();
}

EXPORT("tics") unsigned wd_tics(void)
{
    return (unsigned)clock_tics;
}

EXPORT("framebuffer") const unsigned char* wd_framebuffer(void)
{
    return doom_get_framebuffer(4);
}

EXPORT("sound") const unsigned char* wd_sound(void)
{
    const unsigned char* raw = (const unsigned char*)doom_get_sound_buffer();
    int i;
    for (i = 0; i < 2048; i++)
        sound_copy[i] = raw[i];
    return sound_copy;
}

EXPORT("key_down") void wd_key_down(int key)
{
    doom_key_down((doom_key_t)key);
}

EXPORT("key_up") void wd_key_up(int key)
{
    doom_key_up((doom_key_t)key);
}

EXPORT("button_down") void wd_button_down(int button)
{
    doom_button_down((doom_button_t)button);
}

EXPORT("button_up") void wd_button_up(int button)
{
    doom_button_up((doom_button_t)button);
}

EXPORT("alloc") void* wd_alloc(int size)
{
    return heap_alloc(size);
}

EXPORT("release") void wd_release(void* ptr)
{
    heap_release(ptr);
}
