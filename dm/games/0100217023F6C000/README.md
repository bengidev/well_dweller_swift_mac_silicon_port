# Well Dweller (`0100217023F6C000`)

Version 1.0.0, SDK **22.2.0** (`nnSdk-22_2_0`, `NintendoSDK_NVN-22_2_0`, `NintendoSDK_OpenGL-22_2_0`). A **GameMaker Studio 2** game: the RomFS holds the runner's data file (`game.win`, 229 MB, `FORM`/`GEN8`), its entitlements, three `audiogroup*.dat` banks, `options.ini` with `[LLVM-Switch] SDKDir=…`, and its pictures.

It renders with **OpenGL**, not NVN: `main` imports exactly nine EGL entry points (`eglChooseConfig`, `eglCreateContext`, `eglCreateWindowSurface`, `eglDestroySurface`, `eglGetDisplay`, `eglGetProcAddress`, `eglInitialize`, `eglMakeCurrent`, `eglSwapBuffers`) and every GL function through `eglGetProcAddress`. The context is `OpenGL 3.2`. Modules `main`, `subsdk1` (`NintendoSDK_movie`) and `sdk`; `subsdk0` (NVIDIA's GL driver) is never loaded.

On the Mac: the language list, the title screen, the opening story and the first room with its dialog render at 60 fps with sound, played with the keyboard (WASD + J/K) or a pad.

## What it needs

| Setting | Where | Why |
|---|---|---|
| `modules main subsdk1 sdk` | [`game.tsv`](game.tsv) | `main` takes nothing from NVIDIA's GL driver: the GL layer answers its EGL imports, so `subsdk0` stays unloaded |
| `sys_resource 0x0`; `mem_reserve 0x100000000`, `mem_alias 0x10000000`, `mem_stack 0x10000000`, `app_pool 0xCD500000`, `mem_used 0x6a00000` | [`game.tsv`](game.tsv) | the NPDM declares no system resource, so `nninitStartup` gives its malloc a heap of the pool minus used memory (3.10 GB), mapped as it is touched |
| [`gl_capture.tsv`](gl_capture.tsv) | profile | the 93 shaders the runner puts together at run time, which no game file holds; the NSP script captures them on the Mac; see [Shaders](#shaders) |
| `shader_groups /=romfs` | [`game.tsv`](game.tsv) | no NVN shaders: the profile's NVN tables stay empty and the GL library comes from `gl_shaders.py` |

## Rendering (OpenGL)

The runner's own choices, and what the GL layer had to gain for them.

- **Shaders at run time:** the runner writes each variant of its GLSL as text, in **GLSL ES 1.00 without a `#version` line** (`attribute`, `varying`, `gl_FragColor`, `precision mediump`), and names a variable `sample`, which is a reserved word since ES 3.00. `gl_shaders.py`'s `es100()` pass rewrites the dialect to ES 3.10 for SPIR-V: precision statements and `lowp`/`mediump`/`highp` go, `attribute`/`varying` become `in`/`out`, `gl_FragColor` becomes a declared `gm_FragColor`, `sample` becomes `gm_sample`, and a `#version 310 es` header is prepended. Texture functions stay with the existing `fixups()`, which renames them after `glslangValidator -E`, so a macro cannot hide one.
- **Struct uniforms:** a light environment and a few others are `uniform LightEnv { … };` blocks. `gl_shaders.py` now flattens a struct's members into rows of their own (dotted names, `u:u_LightEnv.m_dirLights_dir[0]`), with each nested member's offset added to its parent's: that is what the layer's `glGetUniformLocation` compares against (it strips only the `[n]` element suffix, and the table's name field is 48 bytes).
- **Draws from client memory:** every sprite, the room background and the screen composite are drawn from **client-memory vertex arrays** (`glVertexAttribPointer` with no buffer bound). Metal cannot read guest memory as vertex data, and the layer dropped those draws with one `[RED] vertex attribute 0 reads client memory …` line. `draw_setup` now copies the span the draw touches (from the first to the last vertex, honouring `glDrawElements`' indices) into a transient `MTLBuffer` per draw. Before this the window showed text only, because the runner's text path is the one that uses a real buffer.
- **Two targets:** the runner renders its room into a **1280x720 surface** of its own and composites that surface onto the window with one 4-vertex strip (program 75, `GL_TRIANGLE_STRIP`, sampler on the surface's colour texture). The window is 1920x1080 and the composite's matrix has a negative y scale, since the runner keeps its surfaces y down while the window is y up.
- **`nv::` graphics memory (resolved, a crash at `pc 0`):** the runner asks `nv::GetGraphicsMemoryInfo` for its version string at startup and prints the pool. With no NVN device the SDK's own path dereferences an uninitialised driver object (`ldr x0,[x0]; br x1` with `x0 = 0`), so the five `nv::` symbols `main` imports are answered by [`dm/gfx/hle_nv.c`](../../gfx/hle_nv.c): the allocators are recorded, `InitializeGraphics` takes the pool, and `GetGraphicsMemoryInfo` reports that pool (total and free = its size) or zeroes the structure when nothing was initialised.
- **Small gaps filled while bringing it up:** `glDepthRange` / `glDepthRangef`, `GL_DEPTH_CLAMP` (Metal clamps to the depth range already), `GL_MAX_TEXTURE_MAX_ANISOTROPY_EXT` (16), and `GL_FRAMEBUFFER_BINDING`-style `glGetIntegerv` cases.
- **Bring-up tools now in the layer:** `DM_GL_TRACE=<from>:<to>:<names>` logs the game's GL calls with their arguments in order (an `eglGetProcAddress` name gets a stub that records its registers and then jumps to the real entry, so the order and arguments are the game's own), `DM_GL_DRAWLOG=<n>[:<seconds>]` prints each draw's target, viewport, program, matrices and vertex attributes, `DM_GL_FBLOG=1` logs framebuffer binds, and `DM_GL_FBDUMP=<fb>:<seconds>:<path>[|…]` writes a PNG of a framebuffer at a given time (its rows are bottom up, the vertical flip of what the present shows).

## Shaders

- **Current:** 93 sources in [`gl_capture.tsv`](gl_capture.tsv) — the runner's sprite, text, lighting, fog and outline programs and their variants — captured on the Mac with `DM_GL_CAPTURE` and translated to one `.metallib` by `gl_shaders.py`. The set is stable from boot through the first room's dialog; a room with an effect no earlier scene used would add one, which the capture table makes the build report.

## Threads

- **Resolved: `nn::diag` abort with `Result 0` during `main`'s static initialisers** (`call site sdk+0x153c34`, inside `nn::nlibsdk::heap::TlsHeapCentral::LockMutexSlow`). SDK 22 identifies a critical section's owner by the **32-bit thread id at `ThreadLocalRegion+0x110`** (`InternalCriticalSection::IsLockedByCurrentThread` is `mrs tpidrro_el0; ldr w8,[x8,#0x110]; ldr w9,[x0]; and; cmp; cset`), where SDK 16 used the thread object pointer at +0x1F8. The host left +0x110 at zero, which is the owner word of an unlocked mutex, so every unlocked mutex read as owned by the caller and the first heap lock aborted. `thread.c` now stores a unique, never-zero thread id there as well (SDK 22 still wants +0x1F8). See [threads](../../../docs/reference/threads.md#the-thread-id-at-threadlocalregion0x110-sdk-22).

## Time

- **Resolved: an uncaught `std::system_error` that ended `libc++abi: terminating due to uncaught exception of type …`.** SDK 22's `clock_gettime` is an ifunc family whose `CLOCK_MONOTONIC` slot binds `nn::time::GetStandardSteadyClockCurrentTimespec`, which the host did not answer, so `std::chrono::steady_clock::now()` threw. `hle_time.c` answers that timespec with the host's monotonic clock; the network-clock variants are left unbound. See [services](../../../docs/reference/services.md#clock_gettime-is-nntimes-steady-clock-sdk-22).

## Audio

- **Resolved: no audio at all.** SDK 22 calls **`nn::audio::OpenAudioOut(AudioOut*, const char*, const AudioOutParameter&)`**, without the `SystemEvent` the host only had, so the SDK's own IPC path ran and failed with `Result 0xe15`. `hle_audio.c` gained that overload (the release event stays NULL and the output polls). With `DM_AUDIO=1` on the Mac the first room's music plays: 0 underruns after the boot's first 194 padded callbacks.

## Open

- **`save:/Settings.sav` is never written.** The runner asks the language on every launch (`fs path not found: save:/Settings.sav`, then `save:/Settings.sav` is not on the RomFS either). `save:/WELLDWELLER/blob.sav` is written and committed (`save commit #1 … swapped atomically`), so the save mount works: the settings file is written on a clean quit, which the host's kill does not give the runner.
- **Verified up to the first room's dialog.** Later rooms, the map and the game's own menus are unverified.
- **Audio and video were not measured against each other** (the report of `DM_AUDIO_DUMP` shows music, and the video runs at 60 fps, but no lip-sync or cutscene timing was checked).
