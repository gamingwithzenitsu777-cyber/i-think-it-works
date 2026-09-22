#include <cstdio>
#include <cstring>
#include <cctype>
#include <string>
#include <vector>
#include <algorithm>
#include <fstream>
#include <sstream>

#include "plugincommon.h"
#include "amx/amx.h"

static void (*logprintf)(char* format, ...) = nullptr;
static std::vector<std::string> whitelist;
static const char *DB_FILE = "scriptfiles/ocrp_whitelist.txt";

static std::string trim(const std::string &s) {
    size_t a = 0, b = s.size();
    while (a < b && std::isspace((unsigned char)s[a])) ++a;
    while (b > a && std::isspace((unsigned char)s[b - 1])) --b;
    return s.substr(a, b - a);
}

static bool validName(const std::string &name) {
    if (name.empty() || name.size() > 24) return false;
    size_t underscore = name.find('_');
    if (underscore == std::string::npos || underscore == 0 || underscore == name.size() - 1) return false;
    if (!std::isupper((unsigned char)name[0])) return false;
    if (!std::isupper((unsigned char)name[underscore + 1])) return false;
    for (size_t i = 0; i < name.size(); ++i) {
        if (i == underscore) continue;
        if (i != 0 && i != underscore + 1 && !std::islower((unsigned char)name[i])) return false;
        if (!std::isalpha((unsigned char)name[i]) && name[i] != '_') return false;
    }
    return true;
}

static bool equalName(const std::string &a, const std::string &b) {
    if (a.size() != b.size()) return false;
    for (size_t i = 0; i < a.size(); ++i)
        if (std::tolower((unsigned char)a[i]) != std::tolower((unsigned char)b[i])) return false;
    return true;
}

static void saveDB() {
    std::ofstream out(DB_FILE, std::ios::trunc);
    if (!out) {
        if (logprintf) logprintf((char*)"[OCRP-WHITELIST] Could not write %s", DB_FILE);
        return;
    }
    for (const auto &n : whitelist) out << n << "\n";
}

static void loadDB() {
    whitelist.clear();
    std::ifstream in(DB_FILE);
    if (!in) return;
    std::string line;
    while (std::getline(in, line)) {
        line = trim(line);
        if (validName(line) && std::none_of(whitelist.begin(), whitelist.end(), [&](const std::string &x){ return equalName(x, line); }))
            whitelist.push_back(line);
    }
}

static bool addName(const std::string &name) {
    if (!validName(name)) return false;
    for (const auto &x : whitelist) if (equalName(x, name)) return false;
    whitelist.push_back(name);
    saveDB();
    return true;
}

static bool removeName(const std::string &name) {
    for (auto it = whitelist.begin(); it != whitelist.end(); ++it) {
        if (equalName(*it, name)) {
            whitelist.erase(it);
            saveDB();
            return true;
        }
    }
    return false;
}

static bool isWhitelisted(const std::string &name) {
    for (const auto &x : whitelist) if (equalName(x, name)) return true;
    return false;
}

static bool rconCommand(const std::string &command) {
    std::istringstream iss(command);
    std::string cmd, sub, name;
    iss >> cmd >> sub >> name;
    if (cmd != "whitelist" && cmd != "ocrpwhitelist") return false;
    if (sub == "add" && !name.empty()) return addName(name);
    if (sub == "remove" && !name.empty()) return removeName(name);
    if (sub == "check" && !name.empty()) return isWhitelisted(name);
    return false;
}

static cell AMX_NATIVE_CALL nIsWhitelisted(AMX *amx, cell *params) {
    char *name = nullptr;
    amx_StrParam(amx, params[1], name);
    return name && isWhitelisted(name) ? 1 : 0;
}

static cell AMX_NATIVE_CALL nAddWhitelist(AMX *amx, cell *params) {
    char *name = nullptr;
    amx_StrParam(amx, params[1], name);
    return name && addName(name) ? 1 : 0;
}

static cell AMX_NATIVE_CALL nRemoveWhitelist(AMX *amx, cell *params) {
    char *name = nullptr;
    amx_StrParam(amx, params[1], name);
    return name && removeName(name) ? 1 : 0;
}

static cell AMX_NATIVE_CALL nGetCount(AMX *, cell *) {
    return (cell)whitelist.size();
}

static cell AMX_NATIVE_CALL nHandleRcon(AMX *amx, cell *params) {
    char *cmd = nullptr;
    amx_StrParam(amx, params[1], cmd);
    if (!cmd) return 0;
    return rconCommand(trim(cmd)) ? 1 : 0;
}

static cell AMX_NATIVE_CALL nGetName(AMX *amx, cell *params) {
    int index = (int)params[1];
    if (index < 0 || index >= (int)whitelist.size()) return 0;
    cell *addr = nullptr;
    if (amx_GetAddr(amx, params[2], &addr) != AMX_ERR_NONE) return 0;
    int maxlen = (int)params[3];
    if (maxlen <= 0) return 0;
    amx_SetString(addr, whitelist[index].c_str(), 0, 0, maxlen);
    return 1;
}

static AMX_NATIVE_INFO natives[] = {
    { (char*)"OCRP_IsWhitelisted", nIsWhitelisted },
    { (char*)"OCRP_AddWhitelist", nAddWhitelist },
    { (char*)"OCRP_RemoveWhitelist", nRemoveWhitelist },
    { (char*)"OCRP_GetWhitelistCount", nGetCount },
    { (char*)"OCRP_HandleRconCommand", nHandleRcon },
    { (char*)"OCRP_GetWhitelistName", nGetName },
    { nullptr, nullptr }
};

PLUGIN_EXPORT unsigned int PLUGIN_CALL Supports() {
    return SUPPORTS_VERSION | SUPPORTS_AMX_NATIVES;
}

PLUGIN_EXPORT bool PLUGIN_CALL Load(void **ppData) {
    logprintf = (void (*)(char*, ...))ppData[PLUGIN_DATA_LOGPRINTF];
    loadDB();
    if (logprintf) logprintf((char*)"[OCRP-WHITELIST] Loaded. %d names in database.", (int)whitelist.size());
    return true;
}

PLUGIN_EXPORT void PLUGIN_CALL Unload() {
    saveDB();
    if (logprintf) logprintf((char*)"[OCRP-WHITELIST] Unloaded.");
}

PLUGIN_EXPORT int PLUGIN_CALL AmxLoad(AMX *amx) {
    return amx_Register(amx, natives, -1);
}

PLUGIN_EXPORT int PLUGIN_CALL AmxUnload(AMX *) {
    return AMX_ERR_NONE;
}
