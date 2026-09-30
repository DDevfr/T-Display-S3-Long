#pragma once
#include <Arduino.h>
#include "icon_cache.h"

struct SysData {
    float cpu_pct;
    float cpu_temp;
    float gpu_pct;
    float gpu_temp;
    float ram_pct;
    float ram_total_gb;
    uint8_t cores[16];
    float ssd_read_mbps;
    float ssd_write_mbps;
    float ssd_temp;
    float ssd_used_gb;
    float ssd_total_gb;
    uint8_t ssd_health;
    float ssd2_read_mbps;
    float ssd2_write_mbps;
    float ssd2_temp;
    float ssd2_used_gb;
    float ssd2_total_gb;
    uint8_t ssd2_health;
    float vram_used_mb;
    float vram_total_mb;
    char  wifi_ssid[9];
    float wifi_sig;
    float vpn_on;
    float    net_total_kbps;
    float    cpu_freq_ghz;
    uint8_t  cpu_power_w;
    uint32_t uptime_s;
    char     os_kernel[41];
    uint16_t updates_count;
    uint8_t  screen_on;
    uint8_t  kbd_bat;      // 255 = absent
    uint8_t  kbd_chg;
    uint8_t  mouse_bat;    // 255 = absent
    uint8_t  mouse_chg;
    bool valid;
};

// Parse one CSV line: "CPU:45.2,CTEMP:75.1,GPU:12.5,..."
// Returns true on success.
inline bool parse_sysdata(const char *line, SysData *out) {
    out->valid = false;
    out->wifi_ssid[0] = '\0';
    out->os_kernel[0] = '\0';
    out->ssd_health   = 255;
    out->ssd2_health  = 255;
    out->ssd2_read_mbps = 0.0f;
    out->ssd2_write_mbps = 0.0f;
    out->ssd2_temp = 0.0f;
    out->ssd2_used_gb = 0.0f;
    out->ssd2_total_gb = 0.0f;
    out->net_total_kbps = 0.0f;
    out->cpu_freq_ghz = 0.0f;
    out->cpu_power_w  = 0;
    out->uptime_s     = 0;
    out->updates_count = 0;
    out->screen_on     = 1;
    out->kbd_bat       = 255;
    out->kbd_chg       = 0;
    out->mouse_bat     = 255;
    out->mouse_chg     = 0;
    char buf[512];
    strncpy(buf, line, sizeof(buf) - 1);
    buf[sizeof(buf) - 1] = '\0';

    char *token = strtok(buf, ",");
    while (token != NULL) {
        char *colon = strchr(token, ':');
        if (colon == NULL) { token = strtok(NULL, ","); continue; }
        *colon = '\0';
        const char *key = token;
        float val = atof(colon + 1);

        if      (strcmp(key, "CPU")  == 0) out->cpu_pct     = val;
        else if (strcmp(key, "CTEMP")== 0) out->cpu_temp    = val;
        else if (strcmp(key, "GPU")  == 0) out->gpu_pct     = val;
        else if (strcmp(key, "GTEMP")== 0) out->gpu_temp    = val;
        else if (strcmp(key, "RAM")  == 0) out->ram_pct     = val;
        else if (strcmp(key, "RTOT") == 0) out->ram_total_gb   = val;
        else if (strcmp(key, "SREAD")== 0) out->ssd_read_mbps  = val;
        else if (strcmp(key, "SWRIT")== 0) out->ssd_write_mbps = val;
        else if (strcmp(key, "STEMP")== 0) out->ssd_temp       = val;
        else if (strcmp(key, "SCAP") == 0) out->ssd_used_gb    = val;
        else if (strcmp(key, "STOT") == 0) out->ssd_total_gb    = val;
        else if (strcmp(key, "SHLTH")== 0) out->ssd_health      = (uint8_t)val;
        else if (strcmp(key, "S2RD") == 0) out->ssd2_read_mbps  = val;
        else if (strcmp(key, "S2WR") == 0) out->ssd2_write_mbps = val;
        else if (strcmp(key, "S2TMP")== 0) out->ssd2_temp       = val;
        else if (strcmp(key, "S2CAP")== 0) out->ssd2_used_gb    = val;
        else if (strcmp(key, "S2TOT")== 0) out->ssd2_total_gb   = val;
        else if (strcmp(key, "S2HLTH")== 0) out->ssd2_health    = (uint8_t)val;
        else if (strcmp(key, "VUSED")== 0) out->vram_used_mb    = val;
        else if (strcmp(key, "VTOT") == 0) out->vram_total_mb  = val;
        else if (strcmp(key, "WNAM") == 0) {
            strncpy(out->wifi_ssid, colon + 1, 8);
            out->wifi_ssid[8] = '\0';
        }
        else if (strcmp(key, "WSIG") == 0) out->wifi_sig = val;
        else if (strcmp(key, "VPN")  == 0) out->vpn_on       = val;
        else if (strcmp(key, "NTOT") == 0) out->net_total_kbps = val;
        else if (strcmp(key, "CFRQ") == 0) out->cpu_freq_ghz = val / 10.0f;
        else if (strcmp(key, "CPWR") == 0) out->cpu_power_w  = (uint8_t)val;
        else if (strcmp(key, "UPTS") == 0) out->uptime_s     = (uint32_t)val;
        else if (strcmp(key, "OSKV") == 0) {
            strncpy(out->os_kernel, colon + 1, sizeof(out->os_kernel) - 1);
            out->os_kernel[sizeof(out->os_kernel) - 1] = '\0';
        }
        else if (strcmp(key, "UPD")  == 0) out->updates_count = (uint16_t)val;
        else if (strcmp(key, "SCR")  == 0) out->screen_on     = (uint8_t)val;
        else if (strcmp(key, "KBAT") == 0) out->kbd_bat       = (uint8_t)val;
        else if (strcmp(key, "KCHG") == 0) out->kbd_chg       = (uint8_t)val;
        else if (strcmp(key, "MBAT") == 0) out->mouse_bat     = (uint8_t)val;
        else if (strcmp(key, "MCHG") == 0) out->mouse_chg     = (uint8_t)val;
        else if (key[0] == 'C' && key[1] == 'X') {
            char *p = (char*)(colon + 1);
            for (int i = 0; i < 16; i++) {
                out->cores[i] = (uint8_t)atoi(p);
                p = strchr(p, ';');
                if (!p) break;
                p++;
            }
        }

        token = strtok(NULL, ",");
    }
    out->valid = true;
    return true;
}

// ── Écran 2 : top processus (trame "P:h;pct10;nom|h;pct10;nom|...") ─────────
#define PROC_MAX 12

struct ProcEntry {
    uint32_t icon;      // hash de l'icône, 0 = pas d'icône (pastille)
    uint16_t pct10;     // %CPU façon top × 10 (peut dépasser 1000)
    char     name[16];
};

struct ProcData {
    uint8_t   n;
    ProcEntry e[PROC_MAX];
};

// `line` pointe après le préfixe "P:". Une entrée mal formée est ignorée.
inline bool parse_procs(char *line, ProcData *out) {
    out->n = 0;
    char *save = NULL;
    for (char *tok = strtok_r(line, "|", &save);
         tok != NULL && out->n < PROC_MAX;
         tok = strtok_r(NULL, "|", &save)) {
        char *p1 = strchr(tok, ';');
        char *p2 = p1 ? strchr(p1 + 1, ';') : NULL;
        if (!p2) continue;
        ProcEntry &e = out->e[out->n++];
        e.icon  = strtoul(tok, NULL, 16);
        long pct = strtol(p1 + 1, NULL, 10);
        e.pct10 = pct < 0 ? 0 : (pct > 65535 ? 65535 : (uint16_t)pct);
        strncpy(e.name, p2 + 1, sizeof(e.name) - 1);
        e.name[sizeof(e.name) - 1] = '\0';
    }
    return true;
}

enum FrameType {
    FRAME_NONE,         // pas de ligne complète (ou ligne ignorée)
    FRAME_SYS,          // trame principale → *sys rempli
    FRAME_PROCS,        // trame P: → *procs rempli
    FRAME_ICON,         // trame I: qui a complété une icône valide
};

// Non-blocking serial accumulator; call every loop().
// Renvoie le type de la ligne complète reçue, routée selon son préfixe.
inline FrameType serial_read_line(SysData *sys, ProcData *procs) {
    static char buf[512];
    static int  pos      = 0;
    static bool overflow = false;   // ligne trop longue → rejeter jusqu'au prochain \n

    while (Serial.available()) {
        char c = Serial.read();
        if (c == '\n' || c == '\r') {
            if (pos > 0 && !overflow) {
                buf[pos] = '\0';
                pos      = 0;
                // Le strtok(',') de parse_sysdata ne doit jamais voir P:/I:
                if (buf[0] == 'P' && buf[1] == ':')
                    return parse_procs(buf + 2, procs) ? FRAME_PROCS : FRAME_NONE;
                if (buf[0] == 'I' && buf[1] == ':')
                    return icon_store_chunk(buf + 2) ? FRAME_ICON : FRAME_NONE;
                return parse_sysdata(buf, sys) ? FRAME_SYS : FRAME_NONE;
            }
            pos      = 0;
            overflow = false;
        } else if (pos < (int)sizeof(buf) - 1) {
            buf[pos++] = c;
        } else {
            overflow = true;    // buffer plein : ligne corrompue, on la jette entièrement
        }
    }
    return FRAME_NONE;
}
