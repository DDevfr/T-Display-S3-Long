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
    char buf[256];
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
        else if (strcmp(key, "STOT") == 0) out->ssd_total_gb   = val;
        else if (strcmp(key, "VUSED")== 0) out->vram_used_mb   = val;
        else if (strcmp(key, "VTOT") == 0) out->vram_total_mb  = val;
        else if (strcmp(key, "WNAM") == 0) {
            strncpy(out->wifi_ssid, colon + 1, 8);
            out->wifi_ssid[8] = '\0';
        }
        else if (strcmp(key, "WSIG") == 0) out->wifi_sig = val;
        else if (strcmp(key, "VPN")  == 0) out->vpn_on   = val;
        else if (key[0] == 'C' && key[1] >= '0' && key[1] <= '9') {
            int idx = atoi(key + 1);
            if (idx >= 0 && idx < 16) out->cores[idx] = (uint8_t)val;
        }

        token = strtok(NULL, ",");
    }
    out->valid = true;
    return true;
}

// Non-blocking serial accumulator; call every loop().
// Returns true and fills `out` when a complete line is received.
inline bool serial_read_line(SysData *out) {
    static char buf[256];
    static int pos = 0;

    while (Serial.available()) {
        char c = Serial.read();
        if (c == '\n' || c == '\r') {
            if (pos > 0) {
                buf[pos] = '\0';
                pos = 0;
                return parse_sysdata(buf, out);
            }
        } else if (pos < (int)sizeof(buf) - 1) {
            buf[pos++] = c;
        }
    }
    return false;
}
