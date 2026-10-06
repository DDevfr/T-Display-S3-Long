#pragma once

#include "stdint.h"
#include "pins_config.h"
#include "lvgl.h"/* https://github.com/lvgl/lvgl.git */

#define TFT_RES_H digitalWrite(TFT_QSPI_RST, 1);
#define TFT_RES_L digitalWrite(TFT_QSPI_RST, 0);
#define TFT_CS_H digitalWrite(TFT_QSPI_CS, 1);
#define TFT_CS_L digitalWrite(TFT_QSPI_CS, 0);

typedef struct
{
    uint8_t cmd;
    uint8_t data[36];
    uint8_t len;
} lcd_cmd_t;

void axs15231_init(void);

// Set the display window size
void lcd_address_set(uint16_t x1, uint16_t y1, uint16_t x2, uint16_t y2);
void lcd_PushColors(uint16_t x,
                    uint16_t y,
                    uint16_t width,
                    uint16_t high,
                    uint16_t *data);
void lcd_sleep();
void lcd_wake();

bool get_lcd_spi_dma_write(void);
