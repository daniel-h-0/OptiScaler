#pragma once

// [Hotfix] AuxiliaryDxgiFactoryModules: modules whose DXGI factories create only auxiliary swapchains, such as
// Social Club's overlay in GTA V Enhanced. hooks/Dxgi_Hooks.cpp marks their factories, and their swapchains stay
// native instead of replacing the game's frame-generation swapchain. This is separate from skipDxgiWrapping
// (DllNames.h): that list also holds DirectX runtime callers and is broader than this verified policy.
//
// Parsed strictly: an entry that matched more than intended (a pattern, a path, a part of a name, the game's own
// executable) would keep the game's swapchain out of frame generation without a sign. Entries are DLL file names
// separated by '|', compared whole and case-insensitively; a malformed list keeps the default.
//
// Free of Windows headers: tools/test-auxiliary-modules.py compiles this file on Linux.

#include <algorithm>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace AuxiliaryModules
{
// Social Club's D3D12 renderer (FORK.md, "Social Club auxiliary swapchains")
inline constexpr std::string_view Default = "SocialClubD3D12Renderer.dll";

inline std::string Lower(std::string_view text)
{
    std::string out(text);
    for (char& c : out)
    {
        if (c >= 'A' && c <= 'Z')
            c = static_cast<char>(c - 'A' + 'a');
    }
    return out;
}

// A DLL file name: "<name>.dll", printable ASCII without blanks and without the characters Windows file names
// cannot hold (so no path, drive or wildcard), nor ',' or ';' (a list mistyped with another separator would be
// one name that never matches, and the default would be gone)
inline bool IsModuleName(std::string_view name)
{
    if (name.size() <= 4 || name.size() > 255 || Lower(name.substr(name.size() - 4)) != ".dll")
        return false;

    for (char c : name)
    {
        if (c <= ' ' || c > '~' || std::string_view("\\/:*?\"<>|,;").find(c) != std::string_view::npos)
            return false;
    }

    return true;
}

// The entries in lower case, each once; nullopt when an entry is not a DLL file name (rejected then holds it).
// Blanks around an entry are allowed; an empty entry is not.
inline std::optional<std::vector<std::string>> Parse(std::string_view list, std::string* rejected = nullptr)
{
    std::vector<std::string> names;

    for (size_t start = 0;;)
    {
        const size_t end = list.find('|', start);
        std::string_view entry = list.substr(start, end == std::string_view::npos ? end : end - start);

        while (!entry.empty() && (entry.front() == ' ' || entry.front() == '\t'))
            entry.remove_prefix(1);
        while (!entry.empty() && (entry.back() == ' ' || entry.back() == '\t'))
            entry.remove_suffix(1);

        if (!IsModuleName(entry))
        {
            if (rejected != nullptr)
                *rejected = std::string(entry);

            return std::nullopt;
        }

        if (auto name = Lower(entry); std::find(names.begin(), names.end(), name) == names.end())
            names.push_back(std::move(name));

        if (end == std::string_view::npos)
            return names;

        start = end + 1;
    }
}

// The list in effect: the configured one, or the default when the setting is auto, empty or malformed (rejected
// then holds the first malformed entry, which can be empty)
inline std::vector<std::string> Resolve(const std::optional<std::string>& configured,
                                        std::optional<std::string>& rejected)
{
    rejected.reset();

    if (configured.has_value() && !configured->empty())
    {
        std::string entry;
        if (auto names = Parse(*configured, &entry))
            return *names;

        rejected = entry;
    }

    return *Parse(Default);
}

// module: the caller's file name (Util::WhoIsTheCaller)
inline bool Contains(const std::vector<std::string>& names, std::string_view module)
{
    return std::find(names.begin(), names.end(), Lower(module)) != names.end();
}
} // namespace AuxiliaryModules
