// SPDX-License-Identifier: MIT
// BC250 private addon controls. The addon owns the settings file and applied state.
#pragma once
#include "bc250_fg_contract.h"
#include <cstring>

static void RenderBC250FrameControls()
{
    using Query = BOOL(WINAPI*)(bc250_fg_status*);
    using Read = BOOL(WINAPI*)(bc250_fg_settings*);
    using Save = BOOL(WINAPI*)(const bc250_fg_settings*);
    HMODULE addon = GetModuleHandleW(L"BC250-MFG.asi");
    if (!addon)
        return;
    auto query = reinterpret_cast<Query>(GetProcAddress(addon, "BC250MFGGetFrameSettings"));
    auto read = reinterpret_cast<Read>(GetProcAddress(addon, "BC250MFGReadFrameSettings"));
    auto save = reinterpret_cast<Save>(GetProcAddress(addon, "BC250MFGSaveFrameSettings"));
    if (!query || !read || !save)
        return;

    bc250_fg_status active {};
    active.size = sizeof(active);
    active.version = BC250_FG_SETTINGS_VERSION;
    if (!query(&active))
        return;
    static HMODULE owner = nullptr;
    static bc250_fg_settings selected {};
    static bool saveFailed = false;
    if (owner != addon)
    {
        if (!read(&selected))
            return;
        owner = addon;
    }

    ImGui::PushID("BC250GeneratedFrames");
    ImGui::SeparatorText("XeFG scaling");
    ImGui::TextDisabled("Changes save automatically. Restart the game to apply.");
    bool commit = false;
    if (active.launch_override)
        ImGui::TextWrapped("Resolution is overridden by BC250_XEFG_FRAME_CAP in the launch settings.");
    ImGui::BeginDisabled(active.launch_override != 0);
    const char* modes[] = { "Match output", "Scale", "Limit" };
    int mode = static_cast<int>(selected.resolution);
    if (ImGui::Combo("Resolution", &mode, modes, 3))
    {
        selected.resolution = static_cast<uint32_t>(mode);
        commit = true;
    }
    if (selected.resolution == BC250_FG_SCALE)
    {
        int percent = static_cast<int>(selected.percent);
        if (ImGui::SliderInt("Scale", &percent, 50, 100, "%d%%", ImGuiSliderFlags_AlwaysClamp))
            selected.percent = static_cast<uint32_t>(percent);
        commit |= ImGui::IsItemDeactivatedAfterEdit();
        if (ImGui::IsItemHovered())
            ImGui::SetTooltip("Percentage of output width and height. Game and FSR resolution stay unchanged.");
    }
    else if (selected.resolution == BC250_FG_LIMIT)
    {
        const char* names[] = { "720p", "1080p", "1440p", "2160p" };
        const uint32_t heights[] = { 720, 1080, 1440, 2160 };
        int choice = 1;
        for (int i = 0; i < 4; ++i)
            if (selected.height_limit == heights[i])
                choice = i;
        if (ImGui::Combo("Limit", &choice, names, 4))
        {
            selected.height_limit = heights[choice];
            commit = true;
        }
        if (ImGui::IsItemHovered())
            ImGui::SetTooltip("Fits within a 16:9 resolution limit while preserving aspect ratio. Never exceeds output size.");
    }
    ImGui::EndDisabled();

    const char* filters[] = { "Bilinear", "Area", "Bicubic", "Lanczos2", "FSR1 (EASU)" };
    const auto effectiveMode = active.launch_override ? active.applied.resolution : selected.resolution;
    const bool native = effectiveMode == BC250_FG_OUTPUT ||
                        (effectiveMode == BC250_FG_SCALE && selected.percent == 100);
    ImGui::BeginDisabled(native);
    auto filter = [&](const char* label, uint32_t& value, uint32_t mask) {
        if (value >= 5 || !(mask & (1u << value)))
            return;
        if (ImGui::BeginCombo(label, filters[value]))
        {
            for (uint32_t i = 0; i < 5; ++i)
            {
                if ((mask & (1u << i)) && ImGui::Selectable(filters[i], value == i))
                {
                    value = i;
                    commit = true;
                }
            }
            ImGui::EndCombo();
        }
    };
    filter("Downscale", selected.downscale, active.downscale_mask);
    filter("Upscale", selected.upscale, active.upscale_mask);
    ImGui::EndDisabled();
    if (commit)
        saveFailed = !save(&selected);
    if (saveFailed)
    {
        ImGui::TextUnformatted("Settings could not be saved.");
        ImGui::SameLine();
        if (ImGui::Button("Retry"))
            saveFailed = !save(&selected);
    }
    else if (selected.downscale != active.applied.downscale || selected.upscale != active.applied.upscale ||
             (!active.launch_override && std::memcmp(&selected, &active.applied, sizeof(selected)) != 0))
        ImGui::TextUnformatted("Restart to apply changes.");
    if (active.ready)
        ImGui::Text("FG: %u x %u    Output: %u x %u", active.generated_width, active.generated_height,
                    active.output_width, active.output_height);
    else
        ImGui::TextDisabled("Start frame generation to report dimensions.");
    ImGui::Separator();
    ImGui::PopID();
}
