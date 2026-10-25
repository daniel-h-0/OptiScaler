// SPDX-License-Identifier: MIT
#pragma once

#include <atomic>
#include <mutex>
#include "xell_pace_ctl.h"

// Correct the alternating short/long game-frame starts that can occur when XeLL does not sleep at 3x/4x.
// Output pacing alone cannot correct simulation time. The controller is the one used by the earlier FreeFG
// runtime, called here without SDK hooks. Each XeLL context owns its state; another caller never waits on pacing.
class FreeFGFramePacer
{
    std::atomic<unsigned> factor {0};
    std::atomic<double> last_update {0};
    std::mutex pace_mutex;
    xpc controller {};
    unsigned last_factor = 0;
    DWORD owner_thread = 0;
    double last_call = -1e9;
    uint32_t last_frame = 0;

    static double now()
    {
        static const double scale = [] {
            LARGE_INTEGER frequency;
            QueryPerformanceFrequency(&frequency);
            return 1000.0 / frequency.QuadPart;
        }();
        LARGE_INTEGER counter;
        QueryPerformanceCounter(&counter);
        return counter.QuadPart * scale;
    }

    static void wait_until(double target)
    {
        using Delay = LONG (WINAPI*)(BOOLEAN, LARGE_INTEGER*);
        static auto delay = reinterpret_cast<Delay>(GetProcAddress(GetModuleHandleW(L"ntdll.dll"), "NtDelayExecution"));
        for (;;)
        {
            double left = target - now();
            if (left <= 0)
                return;
            if (left > 0.3 && delay)
            {
                LARGE_INTEGER interval;
                interval.QuadPart = -static_cast<LONGLONG>((left - 0.2) * 10000.0);
                delay(FALSE, &interval);
            }
            else if (left > 1.5)
                Sleep(static_cast<DWORD>(left - 1.0));
            else
                YieldProcessor();
        }
    }

  public:
    FreeFGFramePacer() { xpc_init(&controller, 0.85, 0.95); }

    // Called on Present's existing FG state update, so sleep never dereferences an FG feature being replaced.
    void configure(unsigned multiplier)
    {
        static const bool enabled = [] {
            char value[16] {};
            GetEnvironmentVariableA("BC250_XELL_PACE", value, sizeof(value));
            return value[0] != '0';
        }();
        unsigned selected = 0;
        if (enabled && (multiplier == 3 || multiplier == 4))
        {
            auto module = GetModuleHandleW(L"libxess_fg.dll");
            if (module && GetProcAddress(module, "BC250MFGInitialize"))
                selected = multiplier;
        }
        last_update.store(now());
        factor.store(selected);
    }

    void start(uint32_t frame)
    {
        // A second caller must not serialize behind a held frame. Only the game's current frame thread is paced.
        std::unique_lock lock(pace_mutex, std::try_to_lock);
        if (!lock.owns_lock())
            return;
        double time = now();
        unsigned multiplier = factor.load();
        if (time - last_update.load() > 250.0)
            multiplier = 0;
        if (multiplier != last_factor)
        {
            last_factor = multiplier;
            xpc_restart(&controller, time);
            LOG_INFO("FreeFG frame-start pacing: multiplier {}", multiplier);
        }
        if (!multiplier)
            return;
        DWORD thread = GetCurrentThreadId();
        if (thread != owner_thread)
        {
            if (owner_thread && time - last_call < 250.0)
                return;
            owner_thread = thread;
            xpc_restart(&controller, time);
        }
        if (frame == last_frame && time - last_call < 2.0)
            return;
        last_frame = frame;
        last_call = time;
        bool was_on = controller.on;
        double wait = xpc_wait(&controller, time, 0, -1);
        if (controller.on != was_on)
            LOG_INFO("FreeFG frame-start pacing {} (period {:.3f} ms)", controller.on ? "engaged" : "disengaged",
                     xpc_period(&controller));
        if (wait > 0)
        {
            wait_until(time + wait);
            time = now();
        }
        xpc_started(&controller, time);
    }
};
