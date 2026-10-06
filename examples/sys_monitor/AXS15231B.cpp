#include "AXS15231B.h"
#include "Arduino.h"
#include "driver/spi_master.h"

// Pilote AXS15231B réduit au seul chemin utilisé : QSPI + DMA (pilote LilyGo
// d'origine, branches SPI 4 fils / sans DMA / rotation / dessin direct retirées).

static volatile bool lcd_spi_dma_write = false;
uint32_t transfer_num = 0;
size_t lcd_PushColors_len = 0;

const static lcd_cmd_t axs15231b_qspi_init[] = {
    {0x28, {0x00}, 0x40},
    {0x10, {0x00}, 0x20},
    {0x11, {0x00}, 0x80},
    {0x29, {0x00}, 0x00}, 
};

bool get_lcd_spi_dma_write(void)
{
    return lcd_spi_dma_write;
}

static spi_device_handle_t spi;

static void lcd_send_cmd(uint32_t cmd, uint8_t *dat, uint32_t len)
{
    TFT_CS_L;
    spi_transaction_t t;
    memset(&t, 0, sizeof(t));
    t.flags = (SPI_TRANS_MULTILINE_CMD | SPI_TRANS_MULTILINE_ADDR);
    t.cmd = 0x02;
    t.addr = cmd << 8;
    if (len != 0) {
        t.tx_buffer = dat;
        t.length = 8 * len;
    } else {
        t.tx_buffer = NULL;
        t.length = 0;
    }
    spi_device_polling_transmit(spi, &t);
    TFT_CS_H;
}

static void IRAM_ATTR spi_dma_cd(spi_transaction_t *trans)
{
    if(transfer_num > 0)
    {
        transfer_num--;
    }

    if(lcd_PushColors_len <= 0 && transfer_num <= 0)
    {
        if(lcd_spi_dma_write) {
            lcd_spi_dma_write = false;
            lv_disp_t * disp = _lv_refr_get_disp_refreshing();
            if(disp != NULL)
                lv_disp_flush_ready(disp->driver);

            TFT_CS_H;
        }
    }
}

void axs15231_init(void)
{
    pinMode(TFT_QSPI_CS, OUTPUT);
    pinMode(TFT_QSPI_RST, OUTPUT);

    TFT_RES_H;
    delay(130);
    TFT_RES_L;
    delay(130);
    TFT_RES_H;
    delay(300);

    esp_err_t ret;

    spi_bus_config_t buscfg = {
        .data0_io_num = TFT_QSPI_D0,
        .data1_io_num = TFT_QSPI_D1,
        .sclk_io_num = TFT_QSPI_SCK,
        .data2_io_num = TFT_QSPI_D2,
        .data3_io_num = TFT_QSPI_D3,
        .max_transfer_sz = (SEND_BUF_SIZE * 16) + 8,
        .flags = SPICOMMON_BUSFLAG_MASTER | SPICOMMON_BUSFLAG_GPIO_PINS,
    };
    spi_device_interface_config_t devcfg = {
        .command_bits = 8,
        .address_bits = 24,
        .mode = TFT_SPI_MODE,
        .clock_speed_hz = SPI_FREQUENCY,
        .spics_io_num = -1,   // CS piloté à la main (TFT_CS_L / TFT_CS_H)
        .flags = SPI_DEVICE_HALFDUPLEX,
        .queue_size = 17,
        .post_cb = spi_dma_cd,
    };
    ret = spi_bus_initialize(TFT_SPI_HOST, &buscfg, SPI_DMA_CH_AUTO);
    ESP_ERROR_CHECK(ret);
    ret = spi_bus_add_device(TFT_SPI_HOST, &devcfg, &spi);
    ESP_ERROR_CHECK(ret);

    for (int i = 0; i < sizeof(axs15231b_qspi_init) / sizeof(lcd_cmd_t); i++)
    {
        lcd_send_cmd(axs15231b_qspi_init[i].cmd,
                     (uint8_t *)axs15231b_qspi_init[i].data,
                     axs15231b_qspi_init[i].len & 0x3f);

        if (axs15231b_qspi_init[i].len & 0x80)
            delay(200);
        if (axs15231b_qspi_init[i].len & 0x40)
            delay(20);
    }
}

void lcd_address_set(uint16_t x1, uint16_t y1, uint16_t x2, uint16_t y2)
{
    lcd_cmd_t t[2] = {
        {0x2a, {(uint8_t)(x1 >> 8), (uint8_t)x1, uint8_t(x2 >> 8), (uint8_t)(x2)}, 0x04},
        {0x2b, {(uint8_t)(y1 >> 8), (uint8_t)(y1), (uint8_t)(y2 >> 8), (uint8_t)(y2)}, 0x04},
    };

    for (uint32_t i = 0; i < 2; i++) {
        lcd_send_cmd(t[i].cmd, t[i].data, t[i].len);
    }
}

// Envoi d'une zone par morceaux de SEND_BUF_SIZE pixels, au plus 3 transactions
// DMA en file. Appel avec data == NULL : poursuit l'envoi en cours (loop()).
spi_transaction_ext_t t = {0};
void lcd_PushColors(uint16_t x,
                    uint16_t y,
                    uint16_t width,
                    uint16_t high,
                    uint16_t *data)
{
    static bool first_send = 1;
    static uint16_t *p = (uint16_t *)data;
    static uint32_t transfer_num_old = 0;

    if(data != NULL && (width != 0) && (high != 0))
    {
        lcd_PushColors_len = width * high;
        p = (uint16_t *)data;
        first_send = 1;

        transfer_num = 0;
        lcd_address_set(x, y, x + width - 1, y + high - 1);
        TFT_CS_L;
    }

    // Récupère les résultats des transactions terminées (décomptées par spi_dma_cd)
    uint32_t done = transfer_num_old - transfer_num;
    for (uint32_t i = 0; i < done; i++) {
        spi_transaction_t *rtrans;
        esp_err_t ret = spi_device_get_trans_result(spi, &rtrans, portMAX_DELAY);
        assert(ret == ESP_OK);
    }
    transfer_num_old -= done;

    do {
        if(transfer_num >= 3 || ESP.getFreeHeap() <= 70000)
        {
            break;
        }
        size_t chunk_size = lcd_PushColors_len;

        memset(&t, 0, sizeof(t));
        if (first_send) {
            t.base.flags = SPI_TRANS_MODE_QIO;
            t.base.cmd = 0x32;
            t.base.addr = 0x002C00;
            first_send = 0;
        } else {
            t.base.flags = SPI_TRANS_MODE_QIO | SPI_TRANS_VARIABLE_CMD |
                        SPI_TRANS_VARIABLE_ADDR | SPI_TRANS_VARIABLE_DUMMY;
            t.command_bits = 0;
            t.address_bits = 0;
            t.dummy_bits = 0;
        }
        if (chunk_size > SEND_BUF_SIZE) {
            chunk_size = SEND_BUF_SIZE;
        }
        t.base.tx_buffer = p;
        t.base.length = chunk_size * 16;

        lcd_spi_dma_write = true;

        transfer_num++;
        transfer_num_old++;
        lcd_PushColors_len -= chunk_size;

        ESP_ERROR_CHECK(spi_device_queue_trans(spi, (spi_transaction_t *)&t, portMAX_DELAY));

        p += chunk_size;
    } while (lcd_PushColors_len > 0);
}

void lcd_sleep()
{
    lcd_send_cmd(0x28, NULL, 0);   // display off
    lcd_send_cmd(0x10, NULL, 0);   // sleep in
    delay(5);
}

void lcd_wake()
{
    lcd_send_cmd(0x11, NULL, 0);   // sleep out
    delay(120);
    lcd_send_cmd(0x29, NULL, 0);   // display on
}
