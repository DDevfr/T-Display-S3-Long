#include "lvgl.h"
#include "AXS15231B.h"
#include "ui.h"
#include "serial_parser.h"
#include <Arduino.h>
#include <Wire.h>

// ── Display buffers (double-buffered, PSRAM) ──────────────────────────────────
static lv_disp_draw_buf_t draw_buf;
static lv_color_t *buf;
static lv_color_t *buf1;

// ── Touch ─────────────────────────────────────────────────────────────────────
#define TOUCH_IICSCL 10
#define TOUCH_IICSDA 15
#define TOUCH_RES    16
#define TOUCH_INT    11

#define AXS_TOUCH_ONE_POINT_LEN  6
#define AXS_TOUCH_GESTURE_POS    0
#define AXS_TOUCH_POINT_NUM      1
#define AXS_TOUCH_X_H_POS        2
#define AXS_TOUCH_X_L_POS        3
#define AXS_TOUCH_Y_H_POS        4
#define AXS_TOUCH_Y_L_POS        5

#define AXS_GET_GESTURE_TYPE(b) b[AXS_TOUCH_GESTURE_POS]
#define AXS_GET_POINT_X(b,i) \
    (((uint16_t)(b[AXS_TOUCH_ONE_POINT_LEN*(i)+AXS_TOUCH_X_H_POS] & 0x0F) << 8) \
     + (uint16_t)b[AXS_TOUCH_ONE_POINT_LEN*(i)+AXS_TOUCH_X_L_POS])
#define AXS_GET_POINT_Y(b,i) \
    (((uint16_t)(b[AXS_TOUCH_ONE_POINT_LEN*(i)+AXS_TOUCH_Y_H_POS] & 0x0F) << 8) \
     + (uint16_t)b[AXS_TOUCH_ONE_POINT_LEN*(i)+AXS_TOUCH_Y_L_POS])

static uint8_t touch_cmd[8] = {0xb5, 0xab, 0xa5, 0x5a, 0x00, 0x00, 0x00, 0x08};

void my_disp_flush(lv_disp_drv_t *disp, const lv_area_t *area,
                   lv_color_t *color_p) {
    uint32_t w = area->x2 - area->x1 + 1;
    uint32_t h = area->y2 - area->y1 + 1;
#ifdef LCD_SPI_DMA
    char dummy = 0;
    while (get_lcd_spi_dma_write()) {
        dummy >>= 1;
        lcd_PushColors(0, 0, 0, 0, NULL);
    }
    (void)dummy;
#endif
    lcd_PushColors(area->x1, area->y1, w, h, (uint16_t *)&color_p->full);
#ifndef LCD_SPI_DMA
    lv_disp_flush_ready(disp);
#endif
}

void my_touchpad_read(lv_indev_drv_t *indev_driver, lv_indev_data_t *data) {
    // Pas de toucher → pin HIGH (pull-up) → on évite tout accès I2C
    if (digitalRead(TOUCH_INT) == HIGH) {
        data->state = LV_INDEV_STATE_REL;
        return;
    }
    uint8_t tbuf[20] = {0};
    Wire.beginTransmission(0x3B);
    Wire.write(touch_cmd, 8);
    Wire.endTransmission();
    int nBytes = Wire.requestFrom(0x3B, 8);
    if (nBytes <= 0) {
        data->state = LV_INDEV_STATE_REL;
        return;
    }
    // Timeout 5ms pour éviter de bloquer si l'I2C est lent
    uint32_t t0 = millis();
    while (!Wire.available() && (millis() - t0 < 5));
    if (!Wire.available()) {
        data->state = LV_INDEV_STATE_REL;
        return;
    }
    Wire.readBytes(tbuf, 8);

    uint16_t px = AXS_GET_POINT_X(tbuf, 0);
    uint16_t py = AXS_GET_POINT_Y(tbuf, 0);
    uint16_t gesture = AXS_GET_GESTURE_TYPE(tbuf);

    if (!gesture && (px || py)) {
        px = 640 - px;
        if (px > 640) px = 640;
        if (py > 180) py = 180;
        data->state   = LV_INDEV_STATE_PR;
        data->point.x = py;
        data->point.y = px;
    } else {
        data->state = LV_INDEV_STATE_REL;
    }
}

// ── No-signal timeout (ms) ────────────────────────────────────────────────────
#define NO_SIGNAL_TIMEOUT_MS 5000
static uint32_t last_data_ms = 0;
static bool signal_lost = false;

// ── Setup ─────────────────────────────────────────────────────────────────────
void setup() {
    Serial.setRxBufferSize(512);
    Serial.begin(115200);   // HWCDC (USB-JTAG) — requis pour serial_read_line()

    pinMode(TOUCH_INT, INPUT_PULLUP);
    pinMode(TOUCH_RES, OUTPUT);
    digitalWrite(TOUCH_RES, HIGH); delay(2);
    digitalWrite(TOUCH_RES, LOW);  delay(10);
    digitalWrite(TOUCH_RES, HIGH); delay(50);

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

    Wire.begin(TOUCH_IICSDA, TOUCH_IICSCL);
    delay(10);

    // BQ25896 : stoppe le clignotement de la LED verte sans batterie
    // (reg 0x09 bit5 = BATFET_DIS)
    Wire.beginTransmission(0x6A);
    Wire.write(0x00); Wire.write(0x3F);
    Wire.endTransmission();
    Wire.beginTransmission(0x6A);
    Wire.write(0x09); Wire.write(0x64);
    Wire.endTransmission();

    // Rétroéclairage à 60 % via PWM (5 kHz, 8-bit) pour préserver la LED
    #define BL_PWM_CHANNEL 0
    #define BL_BRIGHTNESS  153   // 0–255 ; 153 ≈ 60 %
    ledcSetup(BL_PWM_CHANNEL, 5000, 8);
    ledcAttachPin(TFT_BL, BL_PWM_CHANNEL);
    ledcWrite(BL_PWM_CHANNEL, BL_BRIGHTNESS);

    axs15231_init();
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

    ui_init();

    last_data_ms = millis();
    signal_lost  = true;
    ui_show_no_signal();
}

extern uint32_t transfer_num;
extern size_t   lcd_PushColors_len;

// ── Loop ──────────────────────────────────────────────────────────────────────
void loop() {
    SysData data;
    if (serial_read_line(&data)) {
        last_data_ms = millis();
        signal_lost  = false;
        ui_update(&data);
    }

    if (!signal_lost && (millis() - last_data_ms > NO_SIGNAL_TIMEOUT_MS)) {
        signal_lost = true;
        ui_show_no_signal();
    }

    delay(1);
    if (transfer_num <= 0 && lcd_PushColors_len <= 0)
        lv_timer_handler();
    if (transfer_num <= 1 && lcd_PushColors_len > 0)
        lcd_PushColors(0, 0, 0, 0, NULL);
}
