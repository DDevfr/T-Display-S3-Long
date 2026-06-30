#pragma once
#include <Arduino.h>

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
    float ssd2_read_mbps;
    float ssd2_write_mbps;
    float ssd2_temp;
    float ssd2_used_gb;
    float ssd2_total_gb;
    float vram_used_mb;
    float vram_total_mb;
    char  wifi_ssid[9];
    float wifi_sig;
    float vpn_on;
    bool valid;
};

// Parse one CSV line: "CPU:45.2,CTEMP:75.1,GPU:12.5,..."
// Returns true on success.
inline bool parse_sysdata(const char *line, SysData *out) {
    out->valid = false;
    out->wifi_ssid[0] = '\0';
    out->ssd2_read_mbps = 0.0f;
    out->ssd2_write_mbps = 0.0f;
    out->ssd2_temp = 0.0f;
    out->ssd2_used_gb = 0.0f;
    out->ssd2_total_gb = 0.0f;
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
        else if (strcmp(key, "S2RD") == 0) out->ssd2_read_mbps  = val;
        else if (strcmp(key, "S2WR") == 0) out->ssd2_write_mbps = val;
        else if (strcmp(key, "S2TMP")== 0) out->ssd2_temp       = val;
        else if (strcmp(key, "S2CAP")== 0) out->ssd2_used_gb    = val;
        else if (strcmp(key, "S2TOT")== 0) out->ssd2_total_gb   = val;
        else if (strcmp(key, "VUSED")== 0) out->vram_used_mb    = val;
        else if (strcmp(key, "VTOT") == 0) out->vram_total_mb  = val;
        else if (strcmp(key, "WNAM") == 0) {
            strncpy(out->wifi_ssid, colon + 1, 8);
            out->wifi_ssid[8] = '\0';
        }
        else if (strcmp(key, "WSIG") == 0) out->wifi_sig = val;
        else if (strcmp(key, "VPN")  == 0) out->vpn_on   = val;
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

// Non-blocking serial accumulator; call every loop().
// Returns true and fills `out` when a complete line is received.
inline bool serial_read_line(SysData *out) {
    static char buf[512];
    static int  pos      = 0;
    static bool overflow = false;   // ligne trop longue → rejeter jusqu'au prochain \n

    while (Serial.available()) {
        char c = Serial.read();
        if (c == '\n' || c == '\r') {
            if (pos > 0 && !overflow) {
                buf[pos] = '\0';
                pos      = 0;
                return parse_sysdata(buf, out);
            }
            pos      = 0;
            overflow = false;
        } else if (pos < (int)sizeof(buf) - 1) {
            buf[pos++] = c;
        } else {
            overflow = true;    // buffer plein : ligne corrompue, on la jette entièrement
        }
    }
    return false;
}
