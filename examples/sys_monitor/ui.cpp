#include "ui.h"

// ── Palette ──────────────────────────────────────────────────────────────────
#define CLR_BG        lv_color_hex(0x0D0D0D)
#define CLR_CPU       lv_color_hex(0xE30613)   // rouge AMD
#define CLR_GPU       lv_color_hex(0x00A8FF)   // bleu Radeon
#define CLR_RAM       lv_color_hex(0x00C87A)   // vert
#define CLR_TEXT      lv_color_hex(0xE0E0E0)
#define CLR_DIM       lv_color_hex(0x2A2A2A)
#define CLR_GRAY      lv_color_hex(0x888888)   // gris R/W inactif
#define CLR_WARN      lv_color_hex(0xFF8C00)   // orange
#define CLR_HOT       lv_color_hex(0xFF2222)   // rouge charge élevée

// ── Layout constants (portrait 180×640) ──────────────────────────────────────
#define SCR_W   180
#define SCR_H   640

// Zones Y
#define Y_HEADER     0
#define Y_CPU       42
#define Y_CORES    170
#define Y_GPU      375
#define Y_RAM      496

// Widget handles
static lv_obj_t *arc_cpu;
static lv_obj_t *lbl_cpu_pct;
static lv_obj_t *lbl_cpu_temp;

static lv_obj_t *arc_gpu;
static lv_obj_t *lbl_gpu_pct;
static lv_obj_t *lbl_gpu_temp;

static lv_obj_t *bar_ram;
static lv_obj_t *lbl_ram;

static lv_obj_t *bar_vram;
static lv_obj_t *lbl_vram;

static lv_obj_t *lbl_ssd_temp,  *lbl_ssd_cap;
static lv_obj_t *lbl_ssd_r,  *lbl_ssd_w,  *bar_ssd,  *lbl_ssd_spd;
static lv_obj_t *lbl_ssd2_temp, *lbl_ssd2_cap;

static lv_obj_t *bars_core[16];

static lv_obj_t *lbl_wifi;
static lv_obj_t *lbl_wifi_pct;
static lv_obj_t *lbl_vpn;

static lv_obj_t *lbl_nosignal;

// ── Helpers ───────────────────────────────────────────────────────────────────

static lv_color_t pct_color(float pct) {
    if (pct < 50.0f) return lv_color_hex(0x00C87A);
    if (pct < 70.0f) return lv_color_hex(0xFFD700);
    if (pct < 85.0f) return lv_color_hex(0xFF8C00);
    return lv_color_hex(0xFF2222);
}

static lv_color_t temp_color(float temp) {
    if (temp < 60.0f) return lv_color_hex(0x00C87A);
    if (temp < 75.0f) return lv_color_hex(0xFFD700);
    if (temp < 85.0f) return lv_color_hex(0xFF8C00);
    return lv_color_hex(0xFF2222);
}

static lv_obj_t *make_arc(lv_obj_t *parent, lv_color_t accent,
                           int x, int y, int size) {
    lv_obj_t *arc = lv_arc_create(parent);
    lv_obj_set_size(arc, size, size);
    lv_obj_set_pos(arc, x, y);

    // Background arc style
    lv_obj_set_style_arc_color(arc, CLR_DIM, LV_PART_MAIN);
    lv_obj_set_style_arc_width(arc, 8, LV_PART_MAIN);

    // Indicator arc style
    lv_obj_set_style_arc_color(arc, accent, LV_PART_INDICATOR);
    lv_obj_set_style_arc_width(arc, 8, LV_PART_INDICATOR);

    // Hide the knob
    lv_obj_set_style_bg_opa(arc, LV_OPA_TRANSP, LV_PART_KNOB);
    lv_obj_set_style_pad_all(arc, 0, LV_PART_KNOB);

    lv_arc_set_bg_angles(arc, 135, 405);  // 270° sweep
    lv_arc_set_range(arc, 0, 100);
    lv_arc_set_value(arc, 0);
    lv_obj_clear_flag(arc, LV_OBJ_FLAG_CLICKABLE);

    return arc;
}

static lv_obj_t *make_label(lv_obj_t *parent, const char *txt,
                             lv_color_t color, const lv_font_t *font,
                             int x, int y) {
    lv_obj_t *lbl = lv_label_create(parent);
    lv_label_set_text(lbl, txt);
    lv_obj_set_style_text_color(lbl, color, 0);
    lv_obj_set_style_text_font(lbl, font, 0);
    lv_obj_set_pos(lbl, x, y);
    return lbl;
}

// ── Public API ────────────────────────────────────────────────────────────────

void ui_init(void) {
    lv_obj_t *scr = lv_scr_act();
    lv_obj_set_style_bg_color(scr, CLR_BG, 0);
    lv_obj_set_style_bg_opa(scr, LV_OPA_COVER, 0);

    // ── Header ───────────────────────────────────────────────────────────────
    lv_obj_t *hdr = lv_obj_create(scr);
    lv_obj_set_size(hdr, SCR_W, 42);
    lv_obj_set_pos(hdr, 0, Y_HEADER);
    lv_obj_set_style_bg_color(hdr, lv_color_hex(0x1A0000), 0);
    lv_obj_set_style_border_width(hdr, 0, 0);
    lv_obj_set_style_radius(hdr, 0, 0);
    lv_obj_set_style_pad_all(hdr, 0, 0);

    // Ligne 1 : SSID + barres (gauche, font_12)
    lbl_wifi = lv_label_create(hdr);
    lv_label_set_text(lbl_wifi, "WiFi --");
    lv_obj_set_style_text_color(lbl_wifi, CLR_TEXT, 0);
    lv_obj_set_style_text_font(lbl_wifi, &lv_font_montserrat_12, 0);
    lv_obj_set_pos(lbl_wifi, 4, 2);

    // Ligne 1 : VPN (droite, font_12)
    lbl_vpn = lv_label_create(hdr);
    lv_label_set_text(lbl_vpn, "VPN --");
    lv_obj_set_style_text_color(lbl_vpn, lv_color_hex(0x555555), 0);
    lv_obj_set_style_text_font(lbl_vpn, &lv_font_montserrat_12, 0);
    lv_obj_align(lbl_vpn, LV_ALIGN_TOP_RIGHT, -4, 2);

    // Ligne 2 : % WiFi (gauche, font_14, coloré)
    lbl_wifi_pct = lv_label_create(hdr);
    lv_label_set_text(lbl_wifi_pct, "--%");
    lv_obj_set_style_text_color(lbl_wifi_pct, CLR_TEXT, 0);
    lv_obj_set_style_text_font(lbl_wifi_pct, &lv_font_montserrat_14, 0);
    lv_obj_set_pos(lbl_wifi_pct, 4, 22);

    // ── CPU section ──────────────────────────────────────────────────────────
    // Arc (170px zone → arc 120px centré)
    arc_cpu = make_arc(scr, CLR_CPU, (SCR_W - 120) / 2, Y_CPU + 10, 120);

    // % utilisation (grand, centre)
    lbl_cpu_pct = lv_label_create(scr);
    lv_label_set_text(lbl_cpu_pct, "--%");
    lv_obj_set_style_text_color(lbl_cpu_pct, CLR_TEXT, 0);
    lv_obj_set_style_text_font(lbl_cpu_pct, &lv_font_montserrat_20, 0);
    lv_obj_set_style_text_align(lbl_cpu_pct, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_align_to(lbl_cpu_pct, arc_cpu, LV_ALIGN_CENTER, 0, -8);

    // Température (sous le %)
    lbl_cpu_temp = lv_label_create(scr);
    lv_label_set_text(lbl_cpu_temp, "--\xc2\xb0""C");
    lv_obj_set_style_text_color(lbl_cpu_temp, CLR_WARN, 0);
    lv_obj_set_style_text_font(lbl_cpu_temp, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_align(lbl_cpu_temp, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_align_to(lbl_cpu_temp, arc_cpu, LV_ALIGN_CENTER, 0, +14);

    // "CPU" dans le gap bas de l'arc (zone sans trait, 90° en bas)
    lv_obj_t *lbl_cpu_name = lv_label_create(scr);
    lv_label_set_text(lbl_cpu_name, "CPU");
    lv_obj_set_style_text_color(lbl_cpu_name, lv_color_hex(0x888888), 0);
    lv_obj_set_style_text_font(lbl_cpu_name, &lv_font_montserrat_10, 0);
    lv_obj_set_style_text_align(lbl_cpu_name, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_align_to(lbl_cpu_name, arc_cpu, LV_ALIGN_CENTER, 0, +38);

    lv_obj_t *lbl_cpu_model = lv_label_create(scr);
    lv_label_set_text(lbl_cpu_model, "Ryzen 9 7940HS");
    lv_obj_set_style_text_color(lbl_cpu_model, lv_color_hex(0x666666), 0);
    lv_obj_set_style_text_font(lbl_cpu_model, &lv_font_montserrat_8, 0);
    lv_obj_set_style_text_align(lbl_cpu_model, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_align_to(lbl_cpu_model, arc_cpu, LV_ALIGN_CENTER, 0, +51);

    // Séparateur
    lv_obj_t *sep1 = lv_obj_create(scr);
    lv_obj_set_size(sep1, SCR_W - 20, 1);
    lv_obj_set_pos(sep1, 10, Y_CPU + 133);
    lv_obj_set_style_bg_color(sep1, CLR_DIM, 0);
    lv_obj_set_style_border_width(sep1, 0, 0);
    lv_obj_set_style_radius(sep1, 0, 0);

    // ── Per-core bars ────────────────────────────────────────────────────────
    // 16 barres en 2 rangées × 8 colonnes dans 200px de hauteur
    // Chaque barre : largeur 14px, espacement 8px, hauteur variable (max 70px)
    const int BAR_W    = 14;
    const int BAR_MAXH = 68;
    const int COL_GAP  = 8;  // entre barres dans une rangée
    const int ROW_GAP  = 14; // entre les 2 rangées
    const int COLS     = 8;
    // total width = 8*(14+8)-8 = 8*22-8 = 168px → centré dans 180px → offset=6
    const int X_OFF    = 6;

    for (int i = 0; i < 16; i++) {
        int row = i / COLS;
        int col = i % COLS;
        int bx  = X_OFF + col * (BAR_W + COL_GAP);
        int by  = Y_CORES + row * (BAR_MAXH + ROW_GAP + 10) + 16;

        // Conteneur de la barre (fond)
        lv_obj_t *cont = lv_obj_create(scr);
        lv_obj_set_size(cont, BAR_W, BAR_MAXH);
        lv_obj_set_pos(cont, bx, by);
        lv_obj_set_style_bg_color(cont, CLR_DIM, 0);
        lv_obj_set_style_border_width(cont, 0, 0);
        lv_obj_set_style_radius(cont, 3, 0);
        lv_obj_set_style_pad_all(cont, 0, 0);

        // Barre LVGL verticale
        lv_obj_t *bar = lv_bar_create(cont);
        lv_bar_set_range(bar, 0, 100);
        lv_bar_set_value(bar, 0, LV_ANIM_OFF);
        lv_obj_set_size(bar, BAR_W, BAR_MAXH);
        lv_obj_set_pos(bar, 0, 0);
        lv_obj_set_style_bg_color(bar, CLR_DIM, LV_PART_MAIN);
        lv_obj_set_style_bg_color(bar, CLR_RAM, LV_PART_INDICATOR);
        lv_obj_set_style_radius(bar, 3, LV_PART_MAIN);
        lv_obj_set_style_radius(bar, 3, LV_PART_INDICATOR);
        lv_obj_set_style_border_width(bar, 0, LV_PART_MAIN);

        // Direction verticale (bas→haut)
        lv_bar_set_mode(bar, LV_BAR_MODE_NORMAL);
        bars_core[i] = bar;

        // Numéro sous chaque barre (toutes rangées)
        lv_obj_t *lbl_n = lv_label_create(scr);
        char nbuf[4];
        snprintf(nbuf, sizeof(nbuf), "%d", i);
        lv_label_set_text(lbl_n, nbuf);
        lv_obj_set_style_text_color(lbl_n, lv_color_hex(0x666666), 0);
        lv_obj_set_style_text_font(lbl_n, &lv_font_montserrat_8, 0);
        lv_obj_set_pos(lbl_n, bx + 2, by + BAR_MAXH + 2);
    }

    // Séparateur
    lv_obj_t *sep2 = lv_obj_create(scr);
    lv_obj_set_size(sep2, SCR_W - 20, 1);
    lv_obj_set_pos(sep2, 10, Y_GPU - 4);
    lv_obj_set_style_bg_color(sep2, CLR_DIM, 0);
    lv_obj_set_style_border_width(sep2, 0, 0);
    lv_obj_set_style_radius(sep2, 0, 0);

    // ── GPU section ──────────────────────────────────────────────────────────
    arc_gpu = make_arc(scr, CLR_GPU, (SCR_W - 100) / 2, Y_GPU + 8, 100);

    // % utilisation (grand, centre)
    lbl_gpu_pct = lv_label_create(scr);
    lv_label_set_text(lbl_gpu_pct, "--%");
    lv_obj_set_style_text_color(lbl_gpu_pct, CLR_TEXT, 0);
    lv_obj_set_style_text_font(lbl_gpu_pct, &lv_font_montserrat_20, 0);
    lv_obj_set_style_text_align(lbl_gpu_pct, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_align_to(lbl_gpu_pct, arc_gpu, LV_ALIGN_CENTER, 0, -7);

    // Température (sous le %)
    lbl_gpu_temp = lv_label_create(scr);
    lv_label_set_text(lbl_gpu_temp, "--\xc2\xb0""C");
    lv_obj_set_style_text_color(lbl_gpu_temp, lv_color_hex(0x7FCCFF), 0);
    lv_obj_set_style_text_font(lbl_gpu_temp, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_align(lbl_gpu_temp, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_align_to(lbl_gpu_temp, arc_gpu, LV_ALIGN_CENTER, 0, +11);

    // "GPU" dans le gap bas de l'arc
    lv_obj_t *lbl_gpu_name = lv_label_create(scr);
    lv_label_set_text(lbl_gpu_name, "GPU");
    lv_obj_set_style_text_color(lbl_gpu_name, lv_color_hex(0x888888), 0);
    lv_obj_set_style_text_font(lbl_gpu_name, &lv_font_montserrat_10, 0);
    lv_obj_set_style_text_align(lbl_gpu_name, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_align_to(lbl_gpu_name, arc_gpu, LV_ALIGN_CENTER, 0, +30);

    lv_obj_t *lbl_gpu_model = lv_label_create(scr);
    lv_label_set_text(lbl_gpu_model, "Radeon 780M");
    lv_obj_set_style_text_color(lbl_gpu_model, lv_color_hex(0x666666), 0);
    lv_obj_set_style_text_font(lbl_gpu_model, &lv_font_montserrat_8, 0);
    lv_obj_set_style_text_align(lbl_gpu_model, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_align_to(lbl_gpu_model, arc_gpu, LV_ALIGN_CENTER, 0, +43);

    // Séparateur
    lv_obj_t *sep3 = lv_obj_create(scr);
    lv_obj_set_size(sep3, SCR_W - 20, 1);
    lv_obj_set_pos(sep3, 10, Y_RAM - 4);
    lv_obj_set_style_bg_color(sep3, CLR_DIM, 0);
    lv_obj_set_style_border_width(sep3, 0, 0);
    lv_obj_set_style_radius(sep3, 0, 0);

    // ── RAM section ──────────────────────────────────────────────────────────
    make_label(scr, "RAM", CLR_TEXT,
               &lv_font_montserrat_10, 8, Y_RAM + 0);
    lbl_ram = lv_label_create(scr);
    lv_label_set_text(lbl_ram, "--/-- GB");
    lv_obj_set_style_text_color(lbl_ram, CLR_TEXT, 0);
    lv_obj_set_style_text_font(lbl_ram, &lv_font_montserrat_10, 0);
    lv_obj_set_width(lbl_ram, SCR_W - 16);
    lv_obj_set_style_text_align(lbl_ram, LV_TEXT_ALIGN_RIGHT, 0);
    lv_obj_set_pos(lbl_ram, 8, Y_RAM + 0);

    bar_ram = lv_bar_create(scr);
    lv_bar_set_range(bar_ram, 0, 100);
    lv_bar_set_value(bar_ram, 0, LV_ANIM_OFF);
    lv_obj_set_size(bar_ram, SCR_W - 16, 14);
    lv_obj_set_pos(bar_ram, 8, Y_RAM + 13);
    lv_obj_set_style_bg_color(bar_ram, CLR_DIM, LV_PART_MAIN);
    lv_obj_set_style_bg_color(bar_ram, CLR_RAM, LV_PART_INDICATOR);
    lv_obj_set_style_radius(bar_ram, 4, LV_PART_MAIN);
    lv_obj_set_style_radius(bar_ram, 4, LV_PART_INDICATOR);
    lv_obj_set_style_border_width(bar_ram, 0, LV_PART_MAIN);

    // ── VRAM section ─────────────────────────────────────────────────────────
    make_label(scr, "VRAM", CLR_TEXT,
               &lv_font_montserrat_10, 8, Y_RAM + 30);
    lbl_vram = lv_label_create(scr);
    lv_label_set_text(lbl_vram, "--/-- GB");
    lv_obj_set_style_text_color(lbl_vram, CLR_TEXT, 0);
    lv_obj_set_style_text_font(lbl_vram, &lv_font_montserrat_10, 0);
    lv_obj_set_width(lbl_vram, SCR_W - 16);
    lv_obj_set_style_text_align(lbl_vram, LV_TEXT_ALIGN_RIGHT, 0);
    lv_obj_set_pos(lbl_vram, 8, Y_RAM + 30);

    bar_vram = lv_bar_create(scr);
    lv_bar_set_range(bar_vram, 0, 100);
    lv_bar_set_value(bar_vram, 0, LV_ANIM_OFF);
    lv_obj_set_size(bar_vram, SCR_W - 16, 14);
    lv_obj_set_pos(bar_vram, 8, Y_RAM + 43);
    lv_obj_set_style_bg_color(bar_vram, CLR_DIM, LV_PART_MAIN);
    lv_obj_set_style_bg_color(bar_vram, CLR_GPU, LV_PART_INDICATOR);
    lv_obj_set_style_radius(bar_vram, 4, LV_PART_MAIN);
    lv_obj_set_style_radius(bar_vram, 4, LV_PART_INDICATOR);
    lv_obj_set_style_border_width(bar_vram, 0, LV_PART_MAIN);

    // ── SSD section ──────────────────────────────────────────────────────────
    // SSD1
    lv_obj_t *sep_ssd = lv_obj_create(scr);
    lv_obj_set_size(sep_ssd, SCR_W - 20, 1);
    lv_obj_set_pos(sep_ssd, 10, Y_RAM + 61);
    lv_obj_set_style_bg_color(sep_ssd, CLR_DIM, 0);
    lv_obj_set_style_border_width(sep_ssd, 0, 0);
    lv_obj_set_style_radius(sep_ssd, 0, 0);

    make_label(scr, "SSD1", CLR_TEXT, &lv_font_montserrat_10, 8, Y_RAM + 65);
    lbl_ssd_temp = lv_label_create(scr);
    lv_label_set_text(lbl_ssd_temp, "--\xc2\xb0""C");
    lv_obj_set_style_text_color(lbl_ssd_temp, CLR_TEXT, 0);
    lv_obj_set_style_text_font(lbl_ssd_temp, &lv_font_montserrat_10, 0);
    lv_obj_set_width(lbl_ssd_temp, SCR_W - 16);
    lv_obj_set_style_text_align(lbl_ssd_temp, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_set_pos(lbl_ssd_temp, 8, Y_RAM + 65);
    lbl_ssd_cap = lv_label_create(scr);
    lv_label_set_text(lbl_ssd_cap, "--/-- GB");
    lv_obj_set_style_text_color(lbl_ssd_cap, CLR_TEXT, 0);
    lv_obj_set_style_text_font(lbl_ssd_cap, &lv_font_montserrat_10, 0);
    lv_obj_set_width(lbl_ssd_cap, SCR_W - 16);
    lv_obj_set_style_text_align(lbl_ssd_cap, LV_TEXT_ALIGN_RIGHT, 0);
    lv_obj_set_pos(lbl_ssd_cap, 8, Y_RAM + 65);

    lbl_ssd_r = make_label(scr, "R", CLR_GRAY, &lv_font_montserrat_10,  8, Y_RAM + 81);
    make_label(scr, "-", lv_color_hex(0x555555), &lv_font_montserrat_10, 14, Y_RAM + 81);
    lbl_ssd_w = make_label(scr, "W", CLR_GRAY, &lv_font_montserrat_10, 20, Y_RAM + 81);
    bar_ssd = lv_bar_create(scr);
    lv_bar_set_range(bar_ssd, 0, 100);
    lv_bar_set_value(bar_ssd, 0, LV_ANIM_OFF);
    lv_obj_set_size(bar_ssd, 90, 16);
    lv_obj_set_pos(bar_ssd, 30, Y_RAM + 79);
    lv_obj_set_style_bg_color(bar_ssd, CLR_DIM, LV_PART_MAIN);
    lv_obj_set_style_bg_color(bar_ssd, CLR_RAM, LV_PART_INDICATOR);
    lv_obj_set_style_radius(bar_ssd, 4, LV_PART_MAIN);
    lv_obj_set_style_radius(bar_ssd, 4, LV_PART_INDICATOR);
    lv_obj_set_style_border_width(bar_ssd, 0, LV_PART_MAIN);
    lbl_ssd_spd = lv_label_create(scr);
    lv_label_set_text(lbl_ssd_spd, "-- MB/s ");
    lv_obj_set_style_text_color(lbl_ssd_spd, CLR_TEXT, 0);
    lv_obj_set_style_text_font(lbl_ssd_spd, &lv_font_montserrat_10, 0);
    lv_obj_set_width(lbl_ssd_spd, SCR_W - 124);
    lv_obj_set_style_text_align(lbl_ssd_spd, LV_TEXT_ALIGN_RIGHT, 0);
    lv_obj_set_pos(lbl_ssd_spd, 122, Y_RAM + 81);

    // SSD2
    lv_obj_t *sep_ssd2 = lv_obj_create(scr);
    lv_obj_set_size(sep_ssd2, SCR_W - 20, 1);
    lv_obj_set_pos(sep_ssd2, 10, Y_RAM + 97);
    lv_obj_set_style_bg_color(sep_ssd2, CLR_DIM, 0);
    lv_obj_set_style_border_width(sep_ssd2, 0, 0);
    lv_obj_set_style_radius(sep_ssd2, 0, 0);

    make_label(scr, "SSD2", CLR_TEXT, &lv_font_montserrat_10, 8, Y_RAM + 101);
    lbl_ssd2_temp = lv_label_create(scr);
    lv_label_set_text(lbl_ssd2_temp, "--\xc2\xb0""C");
    lv_obj_set_style_text_color(lbl_ssd2_temp, CLR_TEXT, 0);
    lv_obj_set_style_text_font(lbl_ssd2_temp, &lv_font_montserrat_10, 0);
    lv_obj_set_width(lbl_ssd2_temp, SCR_W - 16);
    lv_obj_set_style_text_align(lbl_ssd2_temp, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_set_pos(lbl_ssd2_temp, 8, Y_RAM + 101);
    lbl_ssd2_cap = lv_label_create(scr);
    lv_label_set_text(lbl_ssd2_cap, "--/-- GB");
    lv_obj_set_style_text_color(lbl_ssd2_cap, CLR_TEXT, 0);
    lv_obj_set_style_text_font(lbl_ssd2_cap, &lv_font_montserrat_10, 0);
    lv_obj_set_width(lbl_ssd2_cap, SCR_W - 16);
    lv_obj_set_style_text_align(lbl_ssd2_cap, LV_TEXT_ALIGN_RIGHT, 0);
    lv_obj_set_pos(lbl_ssd2_cap, 8, Y_RAM + 101);


    // ── No-signal overlay ────────────────────────────────────────────────────
    lbl_nosignal = lv_label_create(scr);
    lv_label_set_text(lbl_nosignal, "En attente du PC...");
    lv_obj_set_style_text_color(lbl_nosignal, lv_color_hex(0x555555), 0);
    lv_obj_set_style_text_font(lbl_nosignal, &lv_font_montserrat_12, 0);
    lv_obj_align(lbl_nosignal, LV_ALIGN_BOTTOM_MID, 0, -8);
    lv_obj_add_flag(lbl_nosignal, LV_OBJ_FLAG_HIDDEN);
}

void ui_update(const SysData *d) {
    if (!d || !d->valid) { ui_show_no_signal(); return; }

    lv_obj_add_flag(lbl_nosignal, LV_OBJ_FLAG_HIDDEN);

    // WiFi + VPN (header)
    int bars = (int)(d->wifi_sig * 5.0f / 100.0f + 0.5f);
    if (bars > 5) bars = 5;
    char bar_str[6] = ".....";
    for (int i = 0; i < bars; i++) bar_str[i] = '|';
    lv_label_set_text_fmt(lbl_wifi,     "%s %s",  d->wifi_ssid, bar_str);
    lv_label_set_text_fmt(lbl_wifi_pct, "%d%%", (int)d->wifi_sig);
    lv_color_t wc = (d->wifi_sig >= 70) ? lv_color_hex(0x00C87A) :
                    (d->wifi_sig >= 40) ? lv_color_hex(0xFF8C00) :
                                          lv_color_hex(0xFF2222);
    lv_obj_set_style_text_color(lbl_wifi,     wc, 0);
    lv_obj_set_style_text_color(lbl_wifi_pct, wc, 0);
    if ((int)d->vpn_on) {
        lv_label_set_text(lbl_vpn, "VPN ON");
        lv_obj_set_style_text_color(lbl_vpn, lv_color_hex(0x00C87A), 0);
    } else {
        lv_label_set_text(lbl_vpn, "VPN OFF");
        lv_obj_set_style_text_color(lbl_vpn, lv_color_hex(0x555555), 0);
    }

    // CPU arc + labels
    // lv_snprintf (LVGL interne) ne supporte pas %f → cast en int
    lv_arc_set_value(arc_cpu, (int32_t)d->cpu_pct);
    lv_obj_set_style_arc_color(arc_cpu, pct_color(d->cpu_pct), LV_PART_INDICATOR);
    lv_label_set_text_fmt(lbl_cpu_pct, "%d%%", (int)(d->cpu_pct + 0.5f));
    lv_label_set_text_fmt(lbl_cpu_temp, "%d\xc2\xb0""C", (int)(d->cpu_temp + 0.5f));
    lv_obj_set_style_text_color(lbl_cpu_temp, temp_color(d->cpu_temp), 0);

    // GPU arc + labels
    lv_arc_set_value(arc_gpu, (int32_t)d->gpu_pct);
    lv_obj_set_style_arc_color(arc_gpu, pct_color(d->gpu_pct), LV_PART_INDICATOR);
    lv_label_set_text_fmt(lbl_gpu_pct, "%d%%", (int)(d->gpu_pct + 0.5f));
    lv_label_set_text_fmt(lbl_gpu_temp, "%d\xc2\xb0""C", (int)(d->gpu_temp + 0.5f));
    lv_obj_set_style_text_color(lbl_gpu_temp, temp_color(d->gpu_temp), 0);

    // RAM
    lv_bar_set_value(bar_ram, (int32_t)d->ram_pct, LV_ANIM_OFF);
    lv_obj_set_style_bg_color(bar_ram, pct_color(d->ram_pct), LV_PART_INDICATOR);
    float used_gb   = d->ram_total_gb * d->ram_pct / 100.0f;
    int   used_int  = (int)used_gb;
    int   used_frac = (int)((used_gb - used_int) * 10.0f + 0.5f);
    lv_label_set_text_fmt(lbl_ram, "%d.%d/%d GB",
                          used_int, used_frac, (int)(d->ram_total_gb + 0.5f));

    // VRAM
    float vpct = (d->vram_total_mb > 0.0f)
                 ? d->vram_used_mb / d->vram_total_mb * 100.0f : 0.0f;
    lv_bar_set_value(bar_vram, (int32_t)vpct, LV_ANIM_OFF);
    lv_obj_set_style_bg_color(bar_vram, pct_color(vpct), LV_PART_INDICATOR);
    float vused_gb  = d->vram_used_mb / 1024.0f;
    int   vi        = (int)vused_gb;
    int   vf        = (int)((vused_gb - vi) * 10.0f + 0.5f);
    lv_label_set_text_fmt(lbl_vram, "%d.%d/%d GB",
                          vi, vf, (int)(d->vram_total_mb / 1024.0f + 0.5f));

    // SSD — protocole en KB/s, échelle 20 000 KB/s (≈20 MB/s) = 100 %
    #define SSD_ACT   512.0f    // 0.5 MB/s en KB/s
    #define SSD_SCALE 200.0f    // 20 000 KB/s = 100 %

    // SSD1
    float spd1 = d->ssd_read_mbps + d->ssd_write_mbps;   // KB/s
    int   pct1 = (int)(spd1 / SSD_SCALE + 0.5f); if (pct1 > 100) pct1 = 100;
    lv_obj_set_style_text_color(lbl_ssd_r, d->ssd_read_mbps  > SSD_ACT ? CLR_RAM : CLR_GRAY, 0);
    lv_obj_set_style_text_color(lbl_ssd_w, d->ssd_write_mbps > SSD_ACT ? CLR_RAM : CLR_GRAY, 0);
    lv_bar_set_value(bar_ssd, pct1, LV_ANIM_OFF);
    lv_obj_set_style_bg_color(bar_ssd, pct_color(pct1), LV_PART_INDICATOR);
    { int s1 = (int)(spd1 + 0.5f);
      if (s1 >= 10240) lv_label_set_text_fmt(lbl_ssd_spd, "%d MB/s ", s1 / 1024);
      else             lv_label_set_text_fmt(lbl_ssd_spd, "%d KB/s ", s1); }
    if (d->ssd_temp > 0.0f) {
        lv_label_set_text_fmt(lbl_ssd_temp, "%d\xc2\xb0""C", (int)(d->ssd_temp + 0.5f));
        lv_obj_set_style_text_color(lbl_ssd_temp, temp_color(d->ssd_temp), 0);
    } else {
        lv_label_set_text(lbl_ssd_temp, "--\xc2\xb0""C");
        lv_obj_set_style_text_color(lbl_ssd_temp, CLR_DIM, 0);
    }
    if (d->ssd_total_gb > 0.0f)
        lv_label_set_text_fmt(lbl_ssd_cap, "%d/%d GB", (int)d->ssd_used_gb, (int)d->ssd_total_gb);
    else
        lv_label_set_text(lbl_ssd_cap, "--/-- GB");

    // SSD2
    if (d->ssd2_temp > 0.0f) {
        lv_label_set_text_fmt(lbl_ssd2_temp, "%d\xc2\xb0""C", (int)(d->ssd2_temp + 0.5f));
        lv_obj_set_style_text_color(lbl_ssd2_temp, temp_color(d->ssd2_temp), 0);
    } else {
        lv_label_set_text(lbl_ssd2_temp, "--\xc2\xb0""C");
        lv_obj_set_style_text_color(lbl_ssd2_temp, CLR_DIM, 0);
    }
    if (d->ssd2_total_gb > 0.0f)
        lv_label_set_text_fmt(lbl_ssd2_cap, "%d/%d GB", (int)d->ssd2_used_gb, (int)d->ssd2_total_gb);
    else
        lv_label_set_text(lbl_ssd2_cap, "--/-- GB");

    // Per-core bars
    for (int i = 0; i < 16; i++) {
        lv_bar_set_value(bars_core[i], d->cores[i], LV_ANIM_OFF);
        lv_obj_set_style_bg_color(bars_core[i], pct_color(d->cores[i]),
                                   LV_PART_INDICATOR);
    }
}

void ui_show_no_signal(void) {
    lv_obj_clear_flag(lbl_nosignal, LV_OBJ_FLAG_HIDDEN);
}
