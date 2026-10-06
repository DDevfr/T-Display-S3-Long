#include "lvgl.h"
#include "AXS15231B.h"
#include "ui.h"
#include "serial_parser.h"
#include "icon_cache.h"
#include "touch_cst3530.h"
#include <Arduino.h>
#include <Wire.h>

// ── Display buffers (double-buffered, PSRAM) ──────────────────────────────────
static lv_disp_draw_buf_t draw_buf;
static lv_color_t *buf;
static lv_color_t *buf1;

// ── Touch ─────────────────────────────────────────────────────────────────────
// Tactile CST3530 (adresse I2C 0x58, broches dans pins_config.h). Les anciennes
// cartes utilisaient le tactile intégré à l'AXS15231B (0x3B, reset GPIO16
// partagé avec l'écran) : ce code ne les gère plus.

// Bascule écran 1 ⇄ 2 : un nouvel appui compte si le doigt a été levé au moins
// TOUCH_RELEASE_MS (tolère un rapport manqué pendant un appui long) et au
// moins TOUCH_DEBOUNCE_MS après la bascule précédente.
#define TOUCH_RELEASE_MS  150
#define TOUCH_DEBOUNCE_MS 400
static volatile bool page_toggle = false;   // posé par le toucher ou le bouton BOOT

// Bouton BOOT (GPIO0, actif bas) : même bascule que le toucher. Anti-rebond :
// l'état doit rester stable BTN_DEBOUNCE_MS ; la bascule a lieu à l'appui.
#define BTN_DEBOUNCE_MS 30

static void button_poll(void) {
    static bool     stable = HIGH, last_read = HIGH;
    static uint32_t changed_ms = 0;
    bool     r   = digitalRead(PIN_BUTTON_1);
    uint32_t now = millis();
    if (r != last_read) {
        last_read  = r;
        changed_ms = now;
    } else if (r != stable && now - changed_ms >= BTN_DEBOUNCE_MS) {
        stable = r;
        if (stable == LOW) page_toggle = true;
    }
}

static void touch_pressed(void) {
    static uint32_t last_press_ms = 0, last_toggle_ms = 0;
    uint32_t now = millis();
    if (now - last_press_ms > TOUCH_RELEASE_MS &&
        now - last_toggle_ms > TOUCH_DEBOUNCE_MS) {
        page_toggle    = true;
        last_toggle_ms = now;
    }
    last_press_ms = now;
}

void my_disp_flush(lv_disp_drv_t *disp, const lv_area_t *area,
                   lv_color_t *color_p) {
    uint32_t w = area->x2 - area->x1 + 1;
    uint32_t h = area->y2 - area->y1 + 1;
    // Termine l'envoi DMA précédent ; lv_disp_flush_ready() est appelé par le
    // callback DMA (spi_dma_cd) à la fin de celui-ci.
    while (get_lcd_spi_dma_write())
        lcd_PushColors(0, 0, 0, 0, NULL);
    lcd_PushColors(area->x1, area->y1, w, h, (uint16_t *)&color_p->full);
}

void my_touchpad_read(lv_indev_drv_t *indev_driver, lv_indev_data_t *data) {
    uint16_t x, y;
    if (cst3530_read(&x, &y)) {
        data->state   = LV_INDEV_STATE_PR;
        data->point.x = x < EXAMPLE_LCD_H_RES ? x : EXAMPLE_LCD_H_RES - 1;
        data->point.y = y < EXAMPLE_LCD_V_RES ? y : EXAMPLE_LCD_V_RES - 1;
        touch_pressed();
    } else {
        data->state = LV_INDEV_STATE_REL;
    }
}

// ── No-signal timeout (ms) ────────────────────────────────────────────────────
#define NO_SIGNAL_TIMEOUT_MS 5000
static uint32_t last_data_ms = 0;
static bool signal_lost = false;
static uint32_t last_procs_ms = 0;
static bool procs_seen = false;   // trames P: reçues récemment

// ── Rétroéclairage PWM (5 kHz, 8-bit) ─────────────────────────────────────────
#define BL_PWM_CHANNEL 0
#define BL_BRIGHTNESS  153   // 0–255 ; 153 ≈ 60 %

extern uint32_t transfer_num;
extern size_t   lcd_PushColors_len;

// ── Veille écran (pilotée par le champ SCR du NUC) ────────────────────────────
static bool screen_asleep = false;

static void screen_sleep() {
    // Terminer le transfert DMA en cours avant d'envoyer des commandes LCD
    while (transfer_num > 0 || lcd_PushColors_len > 0) {
        if (transfer_num <= 1 && lcd_PushColors_len > 0)
            lcd_PushColors(0, 0, 0, 0, NULL);
        delay(1);
    }
    ledcWrite(BL_PWM_CHANNEL, 0);
    lcd_sleep();
    screen_asleep = true;
}

static void screen_wake() {
    lcd_wake();
    screen_asleep = false;
    lv_obj_invalidate(lv_scr_act());   // redessin complet au prochain lv_timer_handler()
    ledcWrite(BL_PWM_CHANNEL, BL_BRIGHTNESS);
}

// ── Setup ─────────────────────────────────────────────────────────────────────
void setup() {
    Serial.setRxBufferSize(4096);   // trames I: (icônes) en rafale de ~2,9 Ko
    Serial.begin(115200);   // HWCDC (USB-JTAG) — requis pour serial_read_line()
    Serial.setTxTimeoutMs(0);   // « ?I: » ne doit jamais bloquer si le PC ne lit pas

    // 9 impulsions SCL pour libérer un esclave I2C bloqué après un soft-reset
    pinMode(TOUCH_IICSCL, OUTPUT);
    pinMode(TOUCH_IICSDA, INPUT_PULLUP);
    for (int i = 0; i < 9; i++) {
        digitalWrite(TOUCH_IICSCL, HIGH); delayMicroseconds(5);
        digitalWrite(TOUCH_IICSCL, LOW);  delayMicroseconds(5);
    }
    pinMode(TOUCH_IICSDA, OUTPUT);
    digitalWrite(TOUCH_IICSDA, LOW);
    digitalWrite(TOUCH_IICSCL, HIGH); delayMicroseconds(5);
    digitalWrite(TOUCH_IICSDA, HIGH); delayMicroseconds(5);
    pinMode(TOUCH_IICSDA, INPUT);
    pinMode(TOUCH_IICSCL, INPUT);

    Wire.begin(TOUCH_IICSDA, TOUCH_IICSCL);

    // Rétroéclairage à 60 % via PWM pour préserver la LED
    ledcSetup(BL_PWM_CHANNEL, 5000, 8);
    ledcAttachPin(TFT_BL, BL_PWM_CHANNEL);
    ledcWrite(BL_PWM_CHANNEL, BL_BRIGHTNESS);

    axs15231_init();   // se termine par 300 ms d'attente après le reset (GPIO16)
    pinMode(PIN_BUTTON_1, INPUT_PULLUP);   // bouton BOOT : bascule écran 1 ⇄ 2

    // BQ25896 : stoppe le clignotement de la LED verte sans batterie
    // (reg 0x09 bit5 = BATFET_DIS)
    Wire.beginTransmission(0x6A);
    Wire.write(0x00); Wire.write(0x3F);
    Wire.endTransmission();
    Wire.beginTransmission(0x6A);
    Wire.write(0x09); Wire.write(0x64);
    Wire.endTransmission();

    // Même ordre que l'exemple lvgl_demo LilyGo (écran puis tactile). Le pilote
    // partage le port I2C 0 déjà installé par Wire, reset la puce sur GPIO2 et
    // arme l'interruption sur INT.
    cst3530_begin(TOUCH_IICSDA, TOUCH_IICSCL, TOUCH_INT, TOUCH_RES);

    lv_init();

    size_t buffer_size = sizeof(lv_color_t) * EXAMPLE_LCD_H_RES * EXAMPLE_LCD_V_RES;
    buf  = (lv_color_t *)ps_malloc(buffer_size);
    buf1 = (lv_color_t *)ps_malloc(buffer_size);
    if (!buf || !buf1) {
        while (1) delay(1000);   // PSRAM non disponible
    }

    lv_disp_draw_buf_init(&draw_buf, buf, buf1, buffer_size);

    static lv_disp_drv_t disp_drv;
    lv_disp_drv_init(&disp_drv);
    disp_drv.hor_res      = EXAMPLE_LCD_H_RES;
    disp_drv.ver_res      = EXAMPLE_LCD_V_RES;
    disp_drv.flush_cb     = my_disp_flush;
    disp_drv.draw_buf     = &draw_buf;
    disp_drv.full_refresh = 1;
    lv_disp_drv_register(&disp_drv);

    static lv_indev_drv_t indev_drv;
    lv_indev_drv_init(&indev_drv);
    indev_drv.type    = LV_INDEV_TYPE_POINTER;
    indev_drv.read_cb = my_touchpad_read;
    lv_indev_drv_register(&indev_drv);

    icon_cache_init();
    ui_init();

    last_data_ms = millis();
    signal_lost  = true;
    ui_show_no_signal();
}

// ── Loop ──────────────────────────────────────────────────────────────────────
void loop() {
    static SysData  data;
    static ProcData procs;
    // Plusieurs lignes par tour : une icône arrive en 8 lignes I: d'un coup
    for (int i = 0; i < 16; i++) {
        FrameType ft = serial_read_line(&data, &procs);
        if (ft == FRAME_NONE) break;
        if (ft == FRAME_SYS) {
            last_data_ms = millis();
            signal_lost  = false;
            ui_update(&data);
            if (!data.screen_on && !screen_asleep)
                screen_sleep();
            else if (data.screen_on && screen_asleep)
                screen_wake();
        } else if (ft == FRAME_PROCS) {
            last_procs_ms = millis();
            procs_seen    = true;
            ui_update_procs(&procs);
            uint32_t hashes[PROC_MAX];
            for (int j = 0; j < procs.n; j++) hashes[j] = procs.e[j].icon;
            icon_request_missing(hashes, procs.n);
        } else if (ft == FRAME_ICON) {
            ui_refresh_proc_icons();
        }
    }

    // Plus de trame P: (ancien script, PC muet) : vider l'écran 2
    if (procs_seen && millis() - last_procs_ms > NO_SIGNAL_TIMEOUT_MS) {
        procs_seen = false;
        ProcData empty = {};
        ui_update_procs(&empty);
    }

    button_poll();
    if (page_toggle) {
        page_toggle = false;
        ui_toggle_page();
    }

    if (!signal_lost && (millis() - last_data_ms > NO_SIGNAL_TIMEOUT_MS)) {
        signal_lost = true;
        ui_show_no_signal();
        if (screen_asleep)
            screen_wake();   // NUC muet : afficher « no signal » plutôt qu'un écran noir
    }

    delay(1);
    if (screen_asleep)
        return;   // pas de rendu LVGL pendant la veille
    if (transfer_num <= 0 && lcd_PushColors_len <= 0) {
        lv_timer_handler();
    }
    if (transfer_num <= 1 && lcd_PushColors_len > 0)
        lcd_PushColors(0, 0, 0, 0, NULL);
}
